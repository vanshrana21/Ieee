"""
backend/services/certificate_generator.py
Phase 5: Certificate PDF generation service
Isolated service - NEW FILE
"""
import os
import hashlib
from datetime import datetime
from typing import Optional, Tuple
from io import BytesIO

# ReportLab imports for PDF generation
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.pdfgen import canvas
    from reportlab.graphics.shapes import Drawing
    from reportlab.graphics import renderPDF
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

# QR code generation
try:
    import qrcode
    from qrcode.image.pil import PilImage
    QRCODE_AVAILABLE = True
except ImportError:
    QRCODE_AVAILABLE = False

from backend.orm.competition_certificate import CompetitionCertificate, generate_certificate_code


class CertificateGenerator:
    """
    Generates NLSIU-branded PDF certificates with QR verification.
    Uses ReportLab for PDF generation and qrcode for QR codes.
    """
    
    # NLSIU Branding Colors
    NLSIU_MAROON = colors.Color(0.545, 0.0, 0.0)  # #8B0000
    NLSIU_GOLD = colors.Color(0.831, 0.686, 0.216)  # #D4AF37
    CREAM_BG = colors.Color(1.0, 0.992, 0.816)  # #FFFDD0
    
    def __init__(self, upload_dir: str = "uploads/certificates/"):
        self.upload_dir = upload_dir
        self.qr_dir = os.path.join(upload_dir, "qr/")
        os.makedirs(self.upload_dir, exist_ok=True)
        os.makedirs(self.qr_dir, exist_ok=True)
    
    async def generate_certificate(
        self,
        user_id: int,
        user_name: str,
        user_photo_path: Optional[str],
        competition_id: int,
        competition_title: str,
        competition_dates: str,
        team_id: int,
        team_name: str,
        final_rank: int,
        total_score: float,
        base_url: str = "https://juris.ai"
    ) -> Tuple[CompetitionCertificate, str, str]:
        """
        Generate complete certificate with PDF and QR code.
        Returns (certificate_obj, pdf_path, qr_path)
        """
        if not REPORTLAB_AVAILABLE:
            raise ImportError("ReportLab is required for PDF generation. Install with: pip install reportlab")
        
        if not QRCODE_AVAILABLE:
            raise ImportError("qrcode is required for QR generation. Install with: pip install qrcode")
        
        # Generate certificate code
        cert_code = generate_certificate_code()
        
        # File paths
        pdf_filename = f"cert_{cert_code}.pdf"
        pdf_path = os.path.join(self.upload_dir, pdf_filename)
        
        qr_filename = f"qr_{cert_code}.png"
        qr_path = os.path.join(self.qr_dir, qr_filename)
        
        # Generate QR code
        verification_url = f"{base_url}/verify/{cert_code}"
        self._generate_qr_code(verification_url, qr_path)
        
        # Generate PDF
        self._generate_pdf(
            pdf_path=pdf_path,
            user_name=user_name,
            user_photo_path=user_photo_path,
            competition_title=competition_title,
            competition_dates=competition_dates,
            team_name=team_name,
            final_rank=final_rank,
            total_score=total_score,
            cert_code=cert_code,
            qr_path=qr_path,
            verification_url=verification_url
        )
        
        # Calculate digital signature (SHA-256 hash of certificate data)
        cert_data = f"{user_id}:{competition_id}:{team_id}:{final_rank}:{total_score}:{cert_code}:{datetime.utcnow().isoformat()}"
        digital_signature = hashlib.sha256(cert_data.encode()).hexdigest()
        
        # Create certificate object
        certificate = CompetitionCertificate(
            user_id=user_id,
            competition_id=competition_id,
            team_id=team_id,
            final_rank=final_rank,
            total_score=total_score,
            pdf_file_path=pdf_path,
            qr_image_path=qr_path,
            digital_signature=digital_signature
        )
        certificate.certificate_code = cert_code  # Override default
        
        return certificate, pdf_path, qr_path
    
    def _generate_qr_code(self, url: str, output_path: str, size: int = 200):
        """Generate QR code image"""
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4,
        )
        qr.add_data(url)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        img = img.resize((size, size))
        img.save(output_path)
    
    def _generate_pdf(
        self,
        pdf_path: str,
        user_name: str,
        user_photo_path: Optional[str],
        competition_title: str,
        competition_dates: str,
        team_name: str,
        final_rank: int,
        total_score: float,
        cert_code: str,
        qr_path: str,
        verification_url: str
    ):
        """Generate NLSIU-branded certificate PDF"""
        # Create PDF document
        doc = SimpleDocTemplate(
            pdf_path,
            pagesize=A4,
            rightMargin=20*mm,
            leftMargin=20*mm,
            topMargin=20*mm,
            bottomMargin=20*mm
        )
        
        # Container for elements
        elements = []
        
        # Styles
        styles = getSampleStyleSheet()
        
        # Custom styles
        title_style = ParagraphStyle(
            'NLSIUTitle',
            parent=styles['Heading1'],
            fontSize=14,
            textColor=self.NLSIU_MAROON,
            alignment=1,  # Center
            spaceAfter=6
        )
        
        cert_title_style = ParagraphStyle(
            'CertTitle',
            parent=styles['Heading2'],
            fontSize=24,
            textColor=self.NLSIU_GOLD,
            alignment=1,
            spaceAfter=20
        )
        
        name_style = ParagraphStyle(
            'StudentName',
            parent=styles['Heading1'],
            fontSize=28,
            textColor=self.NLSIU_MAROON,
            alignment=1,
            spaceAfter=10
        )
        
        body_style = ParagraphStyle(
            'BodyText',
            parent=styles['Normal'],
            fontSize=12,
            textColor=colors.black,
            alignment=1,
            spaceAfter=8
        )
        
        # Add NLSIU Header
        elements.append(Paragraph("NATIONAL LAW SCHOOL OF INDIA UNIVERSITY", title_style))
        elements.append(Spacer(1, 10))
        
        # Certificate Title
        elements.append(Paragraph("CERTIFICATE OF ACHIEVEMENT", cert_title_style))
        elements.append(Spacer(1, 20))
        
        # Certification text
        cert_text = f"""
        This certifies that<br/><br/>
        """
        elements.append(Paragraph(cert_text, body_style))
        
        # Student Name (prominent)
        elements.append(Paragraph(user_name.upper(), name_style))
        elements.append(Spacer(1, 10))
        
        # Competition details
        details_text = f"""
        has successfully participated in and completed<br/><br/>
        <b>{competition_title}</b><br/>
        held from {competition_dates}<br/><br/>
        as a member of <b>{team_name}</b><br/><br/>
        achieving <b>{self._get_rank_display(final_rank)}</b> with an overall score of <b>{total_score:.2f}/5.0</b>
        """
        elements.append(Paragraph(details_text, body_style))
        elements.append(Spacer(1, 30))
        
        # Date
        issue_date = datetime.now().strftime("%B %d, %Y")
        elements.append(Paragraph(f"Issued on: {issue_date}", body_style))
        elements.append(Spacer(1, 40))
        
        # QR Code and verification section
        qr_data = [
            [Image(qr_path, width=30*mm, height=30*mm), 
             Paragraph(f"<b>Verify Online</b><br/>{verification_url}<br/><br/>Certificate Code:<br/>{cert_code[:16]}...", body_style)]
        ]
        
        qr_table = Table(qr_data, colWidths=[40*mm, 120*mm])
        qr_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        
        elements.append(qr_table)
        elements.append(Spacer(1, 20))
        
        # Digital signature hash
        sig_text = f"Digital Signature: {cert_code}"
        sig_style = ParagraphStyle(
            'Signature',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.gray,
            alignment=1
        )
        elements.append(Paragraph(sig_text, sig_style))
        
        # Build PDF
        doc.build(elements)
    
    def _get_rank_display(self, rank: int) -> str:
        """Get human-readable rank display"""
        rank_suffixes = {1: "st", 2: "nd", 3: "rd"}
        suffix = rank_suffixes.get(rank, "th")
        return f"{rank}{suffix} Place"
    
    def verify_certificate_exists(self, pdf_path: str) -> bool:
        """Check if certificate PDF exists"""
        return os.path.exists(pdf_path)
    
    def get_certificate_bytes(self, pdf_path: str) -> Optional[bytes]:
        """Read certificate PDF as bytes for download"""
        if not os.path.exists(pdf_path):
            return None
        
        with open(pdf_path, 'rb') as f:
            return f.read()


# Placeholder certificate generator for when dependencies aren't installed
class MockCertificateGenerator(CertificateGenerator):
    """Mock generator that creates placeholder certificates when ReportLab/qrcode unavailable"""
    
    async def generate_certificate(self, *args, **kwargs) -> Tuple[CompetitionCertificate, str, str]:
        """Create certificate record without generating actual PDF"""
        cert_code = generate_certificate_code()
        
        pdf_path = os.path.join(self.upload_dir, f"cert_{cert_code}.placeholder")
        qr_path = os.path.join(self.qr_dir, f"qr_{cert_code}.placeholder")
        
        # Write placeholder files
        with open(pdf_path, 'w') as f:
            f.write(f"Placeholder certificate: {cert_code}\n")
        with open(qr_path, 'w') as f:
            f.write(f"Placeholder QR: {cert_code}\n")
        
        # Create certificate object with minimal data
        certificate = CompetitionCertificate(
            user_id=kwargs.get('user_id', 0),
            competition_id=kwargs.get('competition_id', 0),
            team_id=kwargs.get('team_id', 0),
            final_rank=kwargs.get('final_rank', 0),
            total_score=kwargs.get('total_score', 0.0),
            pdf_file_path=pdf_path,
            qr_image_path=qr_path,
            digital_signature=None
        )
        certificate.certificate_code = cert_code
        
        return certificate, pdf_path, qr_path


def get_certificate_generator() -> CertificateGenerator:
    """Factory function to get appropriate certificate generator"""
    if REPORTLAB_AVAILABLE and QRCODE_AVAILABLE:
        return CertificateGenerator()
    else:
        return MockCertificateGenerator()
