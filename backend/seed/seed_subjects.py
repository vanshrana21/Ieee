"""
backend/seed/seed_subjects.py
Seed comprehensive Indian law curriculum subjects (idempotent)
"""
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import select, func
from backend.database import AsyncSessionLocal, init_db
from backend.orm.subject import Subject, SubjectCategory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


SUBJECTS = [
    # ============================================
    # FOUNDATION SUBJECTS (Arts/Commerce/Management)
    # ============================================
    
    # English
    {
        "title": "English I",
        "code": "ENG101",
        "category": SubjectCategory.FOUNDATION,
        "description": "English language and communication skills - Part I",
        "syllabus": "Grammar, comprehension, writing skills, communication"
    },
    {
        "title": "English II",
        "code": "ENG102",
        "category": SubjectCategory.FOUNDATION,
        "description": "English language and communication skills - Part II",
        "syllabus": "Advanced writing, professional communication, presentations"
    },
    
    # Political Science
    {
        "title": "Political Science I",
        "code": "POL101",
        "category": SubjectCategory.FOUNDATION,
        "description": "Introduction to political theory",
        "syllabus": "Political concepts, state, sovereignty, democracy"
    },
    {
        "title": "Political Science II",
        "code": "POL102",
        "category": SubjectCategory.FOUNDATION,
        "description": "Indian political system",
        "syllabus": "Indian constitution, governance, political parties"
    },
    {
        "title": "Political Science III",
        "code": "POL103",
        "category": SubjectCategory.FOUNDATION,
        "description": "Comparative politics",
        "syllabus": "Political systems, comparative analysis, federalism"
    },
    {
        "title": "Political Science IV",
        "code": "POL104",
        "category": SubjectCategory.FOUNDATION,
        "description": "International relations",
        "syllabus": "Global politics, diplomacy, international organizations"
    },
    {
        "title": "Political Science V",
        "code": "POL105",
        "category": SubjectCategory.FOUNDATION,
        "description": "Public administration",
        "syllabus": "Administrative theory, bureaucracy, governance"
    },
    {
        "title": "Political Science VI",
        "code": "POL106",
        "category": SubjectCategory.FOUNDATION,
        "description": "Political philosophy",
        "syllabus": "Classical and modern political thought"
    },
    
    # Economics
    {
        "title": "Economics I",
        "code": "ECO101",
        "category": SubjectCategory.FOUNDATION,
        "description": "Principles of microeconomics",
        "syllabus": "Demand, supply, market structures, consumer behavior"
    },
    {
        "title": "Economics II",
        "code": "ECO102",
        "category": SubjectCategory.FOUNDATION,
        "description": "Principles of macroeconomics",
        "syllabus": "National income, inflation, fiscal policy, monetary policy"
    },
    {
        "title": "Economics III",
        "code": "ECO103",
        "category": SubjectCategory.FOUNDATION,
        "description": "Indian economy",
        "syllabus": "Economic development, planning, reforms, current issues"
    },
    
    # Sociology
    {
        "title": "Sociology I",
        "code": "SOC101",
        "category": SubjectCategory.FOUNDATION,
        "description": "Introduction to sociology",
        "syllabus": "Social structure, institutions, culture, socialization"
    },
    {
        "title": "Sociology II",
        "code": "SOC102",
        "category": SubjectCategory.FOUNDATION,
        "description": "Indian society",
        "syllabus": "Caste, religion, family, social change in India"
    },
    {
        "title": "Sociology III",
        "code": "SOC103",
        "category": SubjectCategory.FOUNDATION,
        "description": "Social problems and policy",
        "syllabus": "Poverty, inequality, social justice, welfare"
    },
    
    # History
    {
        "title": "History I",
        "code": "HIS101",
        "category": SubjectCategory.FOUNDATION,
        "description": "World history",
        "syllabus": "Major civilizations, revolutions, world wars"
    },
    {
        "title": "History II",
        "code": "HIS102",
        "category": SubjectCategory.FOUNDATION,
        "description": "Indian history",
        "syllabus": "Ancient, medieval, modern India, independence movement"
    },
    
    # Psychology
    {
        "title": "Psychology I",
        "code": "PSY101",
        "category": SubjectCategory.FOUNDATION,
        "description": "General psychology",
        "syllabus": "Cognition, learning, personality, development"
    },
    {
        "title": "Psychology II",
        "code": "PSY102",
        "category": SubjectCategory.FOUNDATION,
        "description": "Applied psychology",
        "syllabus": "Organizational behavior, counseling, social psychology"
    },
    
    # Management & Commerce
    {
        "title": "Principles of Management",
        "code": "MGT101",
        "category": SubjectCategory.FOUNDATION,
        "description": "Introduction to management",
        "syllabus": "Planning, organizing, leading, controlling, business functions"
    },
    {
        "title": "Financial Accounting",
        "code": "ACC101",
        "category": SubjectCategory.FOUNDATION,
        "description": "Fundamentals of accounting",
        "syllabus": "Double entry, trial balance, financial statements"
    },
    {
        "title": "Business Communication",
        "code": "COM101",
        "category": SubjectCategory.FOUNDATION,
        "description": "Professional business communication",
        "syllabus": "Written, oral, digital communication for business"
    },
    
    # ============================================
    # CORE LAW SUBJECTS
    # ============================================
    
    # Contract Law
    {
        "title": "Law of Contracts I",
        "code": "LAW201",
        "category": SubjectCategory.CORE,
        "description": "Indian Contract Act, 1872 - Part I",
        "syllabus": "Formation, consideration, capacity, free consent, void agreements"
    },
    {
        "title": "Law of Contracts II",
        "code": "LAW202",
        "category": SubjectCategory.CORE,
        "description": "Indian Contract Act, 1872 - Part II",
        "syllabus": "Performance, discharge, breach, remedies, quasi-contracts"
    },
    
    # Tort Law
    {
        "title": "Law of Torts",
        "code": "LAW203",
        "category": SubjectCategory.CORE,
        "description": "Principles of tortious liability",
        "syllabus": "Negligence, nuisance, defamation, strict liability, defenses"
    },
    
    # Constitutional Law
    {
        "title": "Constitutional Law I",
        "code": "LAW204",
        "category": SubjectCategory.CORE,
        "description": "Indian Constitution - Fundamentals",
        "syllabus": "Preamble, fundamental rights, DPSP, federal structure"
    },
    {
        "title": "Constitutional Law II",
        "code": "LAW205",
        "category": SubjectCategory.CORE,
        "description": "Indian Constitution - Advanced",
        "syllabus": "Parliamentary system, judiciary, emergency provisions, amendments"
    },
    
    # Family Law
    {
        "title": "Family Law I",
        "code": "LAW206",
        "category": SubjectCategory.CORE,
        "description": "Hindu Law",
        "syllabus": "Marriage, divorce, maintenance, adoption, guardianship, succession"
    },
    {
        "title": "Family Law II",
        "code": "LAW207",
        "category": SubjectCategory.CORE,
        "description": "Muslim Law & Special Marriage Act",
        "syllabus": "Muslim personal law, inter-religious marriages, divorce, inheritance"
    },
    
    # Jurisprudence
    {
        "title": "Jurisprudence",
        "code": "LAW208",
        "category": SubjectCategory.CORE,
        "description": "Philosophy and theory of law",
        "syllabus": "Schools of jurisprudence, natural law, positivism, rights, justice"
    },
    
    # Property Law
    {
        "title": "Property Law",
        "code": "LAW209",
        "category": SubjectCategory.CORE,
        "description": "Transfer of Property Act, 1882",
        "syllabus": "Movable and immovable property, transfer, sale, mortgage, lease, gifts"
    },
    
    # Company Law
    {
        "title": "Company Law",
        "code": "LAW210",
        "category": SubjectCategory.CORE,
        "description": "Companies Act, 2013",
        "syllabus": "Incorporation, management, meetings, capital, winding up, corporate governance"
    },
    
    # Administrative Law
    {
        "title": "Administrative Law",
        "code": "LAW211",
        "category": SubjectCategory.CORE,
        "description": "Principles of administrative law",
        "syllabus": "Delegated legislation, administrative tribunals, judicial review, rule of law"
    },
    
    # Public International Law
    {
        "title": "Public International Law",
        "code": "LAW212",
        "category": SubjectCategory.CORE,
        "description": "International legal system",
        "syllabus": "Sources, subjects, territory, treaties, dispute resolution, ICJ"
    },
    
    # Environmental Law
    {
        "title": "Environmental Law",
        "code": "LAW213",
        "category": SubjectCategory.CORE,
        "description": "Environmental protection laws in India",
        "syllabus": "Environment Protection Act, pollution control, sustainable development"
    },
    
    # Criminal Law
    {
        "title": "Criminal Law",
        "code": "LAW214",
        "category": SubjectCategory.CORE,
        "description": "Indian Penal Code, 1860 / Bharatiya Nyaya Sanhita",
        "syllabus": "General principles, offences against person, property, public tranquility, State"
    },
    
    # ============================================
    # PROCEDURAL LAW SUBJECTS
    # ============================================
    
    {
        "title": "Law of Evidence",
        "code": "LAW301",
        "category": SubjectCategory.PROCEDURAL,
        "description": "Indian Evidence Act, 1872 / Bharatiya Sakshya Adhiniyam",
        "syllabus": "Relevancy, admissibility, proof, documentary evidence, witnesses, presumptions"
    },
    {
        "title": "Civil Procedure Code & Limitation",
        "code": "LAW302",
        "category": SubjectCategory.PROCEDURAL,
        "description": "CPC, 1908 and Limitation Act, 1963",
        "syllabus": "Suits, jurisdiction, pleadings, trial procedure, judgments, appeals, execution, limitation"
    },
    {
        "title": "Criminal Procedure Code",
        "code": "LAW303",
        "category": SubjectCategory.PROCEDURAL,
        "description": "CrPC, 1973 / Bharatiya Nagarik Suraksha Sanhita",
        "syllabus": "FIR, investigation, arrest, bail, trial procedure, appeals, revision"
    },
    
    # ============================================
    # PRACTICAL/PROFESSIONAL SUBJECTS
    # ============================================
    
    {
        "title": "Alternative Dispute Resolution",
        "code": "LAW401",
        "category": SubjectCategory.ELECTIVE,
        "description": "ADR mechanisms and mediation",
        "syllabus": "Arbitration, mediation, conciliation, negotiation, Arbitration Act"
    },
    {
        "title": "Drafting Pleading & Conveyancing",
        "code": "LAW402",
        "category": SubjectCategory.PROCEDURAL,
        "description": "Legal drafting and documentation",
        "syllabus": "Pleadings, agreements, deeds, wills, petitions, legal notices"
    },
    {
        "title": "Professional Ethics & Bar Bench Relations",
        "code": "LAW403",
        "category": SubjectCategory.PROCEDURAL,
        "description": "Legal profession and ethics",
        "syllabus": "Advocates Act, professional conduct, ethics, duties, discipline"
    },
    {
        "title": "Moot Court & Advocacy",
        "code": "LAW404",
        "category": SubjectCategory.PROCEDURAL,
        "description": "Practical advocacy skills",
        "syllabus": "Court procedure, arguing, cross-examination, moot court competitions"
    },
    
    # ============================================
    # ELECTIVE SUBJECTS
    # ============================================
    
    {
        "title": "Intellectual Property Law",
        "code": "LAW501",
        "category": SubjectCategory.ELECTIVE,
        "description": "IP rights in India",
        "syllabus": "Patents, trademarks, copyrights, designs, geographical indications"
    },
    {
        "title": "Cyber Law & IT Act",
        "code": "LAW502",
        "category": SubjectCategory.ELECTIVE,
        "description": "Information Technology Act, 2000",
        "syllabus": "Cyber crimes, digital signatures, e-commerce, data protection, intermediary liability"
    },
    {
        "title": "Labour & Industrial Law",
        "code": "LAW503",
        "category": SubjectCategory.ELECTIVE,
        "description": "Labour laws in India",
        "syllabus": "Industrial Disputes Act, Factories Act, minimum wages, social security, labour codes"
    },
    {
        "title": "Banking & Insurance Law",
        "code": "LAW504",
        "category": SubjectCategory.ELECTIVE,
        "description": "Financial sector regulations",
        "syllabus": "Banking Regulation Act, RBI Act, Negotiable Instruments Act, insurance laws"
    },
    {
        "title": "Human Rights Law",
        "code": "LAW505",
        "category": SubjectCategory.ELECTIVE,
        "description": "Human rights and fundamental freedoms",
        "syllabus": "UDHR, ICCPR, NHRC, human rights violations, remedies"
    },
    {
        "title": "Tax Law",
        "code": "LAW506",
        "category": SubjectCategory.ELECTIVE,
        "description": "Income Tax and GST",
        "syllabus": "Income Tax Act, tax computation, GST framework, indirect taxation"
    },
    {
        "title": "Competition Law",
        "code": "LAW507",
        "category": SubjectCategory.ELECTIVE,
        "description": "Competition Act, 2002",
        "syllabus": "Anti-competitive practices, mergers, CCI, abuse of dominance"
    },
    {
        "title": "Women & Law",
        "code": "LAW508",
        "category": SubjectCategory.ELECTIVE,
        "description": "Laws relating to women in India",
        "syllabus": "Domestic violence, sexual harassment, dowry, maternity, gender justice"
    },
    {
        "title": "Consumer Protection Law",
        "code": "LAW509",
        "category": SubjectCategory.ELECTIVE,
        "description": "Consumer Protection Act, 2019",
        "syllabus": "Consumer rights, redressal mechanisms, e-commerce, product liability"
    },
    {
        "title": "Land & Real Estate Law",
        "code": "LAW510",
        "category": SubjectCategory.ELECTIVE,
        "description": "Land laws and real estate regulations",
        "syllabus": "Land acquisition, RERA, tenancy, urban development"
    },
]


async def seed_subjects():
    """Seed subjects table (idempotent)"""
    async with AsyncSessionLocal() as session:
        try:
            logger.info("=" * 60)
            logger.info("SEEDING SUBJECTS")
            logger.info("=" * 60)
            
            created_count = 0
            existing_count = 0
            
            for subject_data in SUBJECTS:
                # Check if subject already exists
                stmt = select(Subject).where(Subject.code == subject_data["code"])
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()
                
                if existing:
                    logger.info(f"✓ Subject {subject_data['title']} exists")
                    existing_count += 1
                    continue
                
                # Create new subject
                subject = Subject(**subject_data)
                session.add(subject)
                logger.info(f"✓ Subject {subject_data['title']} created ({subject_data['category'].value})")
                created_count += 1
            
            await session.commit()
            
            logger.info("=" * 60)
            logger.info(f"RESULT: {created_count} created, {existing_count} already exist")
            logger.info("=" * 60)
            
            # Summary by category
            for category in SubjectCategory:
                stmt = select(func.count(Subject.id)).where(Subject.category == category)
                result = await session.execute(stmt)
                count = result.scalar()
                logger.info(f"  {category.value.capitalize()}: {count} subjects")
            
            # Total
            stmt = select(func.count(Subject.id))
            result = await session.execute(stmt)
            total = result.scalar()
            logger.info(f"\n📚 TOTAL SUBJECTS: {total}")
            
        except Exception as e:
            logger.error(f"❌ Error seeding subjects: {str(e)}")
            await session.rollback()
            raise


async def main():
    """Main entry point"""
    await init_db()
    await seed_subjects()
    logger.info("✅ Subject seeding complete")


if __name__ == "__main__":
    asyncio.run(main())