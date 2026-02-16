"""
backend/services/bulk_upload_service.py
Phase 6: CSV bulk upload service for student account creation
"""
import os
import csv
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.orm.bulk_upload_session import BulkUploadSession, BulkUploadStatus
from backend.orm.user import User, UserRole
from backend.orm.institution import Institution
from backend.auth import get_password_hash

logger = logging.getLogger(__name__)

# Upload directory
UPLOAD_DIR = os.getenv("BULK_UPLOAD_DIR", "uploads/bulk_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


class BulkUploadService:
    """Service for handling bulk CSV uploads of student accounts"""
    
    @classmethod
    async def create_upload_session(
        cls,
        db: AsyncSession,
        institution_id: int,
        uploaded_by_user_id: int,
        csv_file_path: str,
        total_rows: int
    ) -> BulkUploadSession:
        """Create a new bulk upload session"""
        session = BulkUploadSession(
            institution_id=institution_id,
            uploaded_by_user_id=uploaded_by_user_id,
            csv_file_path=csv_file_path,
            total_rows=total_rows,
            status=BulkUploadStatus.PENDING.value,
            processed_rows=0,
            success_count=0,
            error_count=0
        )
        
        db.add(session)
        await db.commit()
        await db.refresh(session)
        
        logger.info(f"Created bulk upload session {session.id} for institution {institution_id}")
        return session
    
    @classmethod
    async def process_csv_file(
        cls,
        db: AsyncSession,
        session_id: int
    ) -> None:
        """
        Process CSV file and create student accounts.
        Target: Process 500 students in <60 seconds.
        """
        # Get session
        result = await db.execute(
            select(BulkUploadSession).where(BulkUploadSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        
        if not session:
            logger.error(f"Upload session {session_id} not found")
            return
        
        # Update status to processing
        session.status = BulkUploadStatus.PROCESSING.value
        session.started_at = datetime.utcnow()
        await db.commit()
        
        # Get institution
        result = await db.execute(
            select(Institution).where(Institution.id == session.institution_id)
        )
        institution = result.scalar_one_or_none()
        
        if not institution:
            session.status = BulkUploadStatus.FAILED.value
            session.completed_at = datetime.utcnow()
            await db.commit()
            logger.error(f"Institution {session.institution_id} not found")
            return
        
        # Prepare error log
        error_log_path = os.path.join(UPLOAD_DIR, f"errors_{session_id}.csv")
        errors = []
        
        try:
            with open(session.csv_file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                for row in reader:
                    try:
                        # Process each row
                        success = await cls._process_student_row(
                            db, session.institution_id, row
                        )
                        
                        if success:
                            session.success_count += 1
                        else:
                            session.error_count += 1
                            errors.append({
                                'row': row,
                                'error': 'Failed to create account'
                            })
                        
                        session.processed_rows += 1
                        
                        # Commit every 10 rows for performance
                        if session.processed_rows % 10 == 0:
                            await db.commit()
                    
                    except Exception as e:
                        session.error_count += 1
                        errors.append({
                            'row': row,
                            'error': str(e)
                        })
                        logger.error(f"Error processing row: {str(e)}")
            
            # Write error log if there are errors
            if errors:
                with open(error_log_path, 'w', newline='', encoding='utf-8') as f:
                    fieldnames = list(errors[0]['row'].keys()) + ['error']
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    for error in errors:
                        row = error['row'].copy()
                        row['error'] = error['error']
                        writer.writerow(row)
                session.error_log_path = error_log_path
            
            # Complete session
            session.status = BulkUploadStatus.COMPLETED.value
            session.completed_at = datetime.utcnow()
            await db.commit()
            
            logger.info(
                f"Bulk upload session {session_id} completed: "
                f"{session.success_count} success, {session.error_count} errors"
            )
        
        except Exception as e:
            session.status = BulkUploadStatus.FAILED.value
            session.completed_at = datetime.utcnow()
            await db.commit()
            logger.error(f"Bulk upload session {session_id} failed: {str(e)}")
    
    @classmethod
    async def _process_student_row(
        cls,
        db: AsyncSession,
        institution_id: int,
        row: Dict[str, str]
    ) -> bool:
        """Process a single student row and create account"""
        try:
            # Extract fields
            name = row.get('name', '').strip()
            email = row.get('email', '').strip().lower()
            roll_number = row.get('roll_number', '').strip()
            year = row.get('year', '').strip()
            course = row.get('course', '').strip()
            
            # Validate required fields
            if not name or not email:
                logger.warning(f"Missing required fields: name={name}, email={email}")
                return False
            
            # Check if user already exists
            result = await db.execute(
                select(User).where(User.email == email)
            )
            existing_user = result.scalar_one_or_none()
            
            if existing_user:
                # Update institution if not set
                if not existing_user.institution_id:
                    existing_user.institution_id = institution_id
                logger.info(f"User {email} already exists, updated institution")
                return True
            
            # Generate password (random, user will use SSO or reset password)
            import secrets
            temp_password = secrets.token_urlsafe(12)
            
            # Create user
            new_user = User(
                email=email,
                name=name,
                hashed_password=get_password_hash(temp_password),
                institution_id=institution_id,
                role=UserRole.student,
                is_active=True
            )
            
            # Set additional metadata if available
            if roll_number:
                # Could store in a profile table or JSON field
                pass
            
            db.add(new_user)
            
            logger.info(f"Created user: {email} for institution {institution_id}")
            return True
        
        except Exception as e:
            logger.error(f"Error processing student row: {str(e)}")
            return False
    
    @classmethod
    async def get_session_status(
        cls,
        db: AsyncSession,
        session_id: int,
        institution_id: int
    ) -> Optional[Dict[str, Any]]:
        """Get upload session status"""
        result = await db.execute(
            select(BulkUploadSession).where(
                BulkUploadSession.id == session_id,
                BulkUploadSession.institution_id == institution_id
            )
        )
        session = result.scalar_one_or_none()
        
        if not session:
            return None
        
        return session.to_dict()
    
    @classmethod
    def validate_csv_format(cls, file_path: str) -> tuple[bool, int, Optional[str]]:
        """
        Validate CSV file format.
        Returns: (is_valid, total_rows, error_message)
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                sample = f.read(1024)
                f.seek(0)
                
                # Detect dialect
                sniffer = csv.Sniffer()
                try:
                    dialect = sniffer.sniff(sample)
                except csv.Error:
                    dialect = None
                
                reader = csv.DictReader(f, dialect=dialect)
                
                # Check required columns
                required_columns = {'name', 'email'}
                headers = set(reader.fieldnames or [])
                
                if not required_columns.issubset(headers):
                    missing = required_columns - headers
                    return False, 0, f"Missing required columns: {', '.join(missing)}"
                
                # Count rows
                row_count = sum(1 for _ in reader)
                
                return True, row_count, None
        
        except Exception as e:
            return False, 0, f"CSV validation error: {str(e)}"


# Convenience function
async def get_bulk_upload_service():
    """Factory function to get bulk upload service instance"""
    return BulkUploadService()
