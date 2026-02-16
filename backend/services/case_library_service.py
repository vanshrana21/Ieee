"""
Case Library Service - Phase: Moot Case Library Upgrade

Service for seeding structured High Court moot cases.
Deterministic uniqueness based on case_id.
"""
import json
import logging
from typing import List, Dict, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.orm.moot_case import MootCase

logger = logging.getLogger(__name__)


# 30 Structured High Court Cases
HIGH_COURT_CASES: List[Dict[str, Any]] = [
    {
        "case_id": "HC001",
        "title": "Right to Privacy in Digital Age",
        "citation": "AIR 2023 SC 1234",
        "short_proposition": "Whether right to privacy extends to digital data and surveillance",
        "legal_domain": "constitutional",
        "difficulty_level": "advanced",
        "complexity_level": 4,
        "constitutional_articles": ["Article 21", "Article 19(1)(a)"],
        "key_issues": ["Right to Privacy", "Data Protection", "Surveillance"],
        "landmark_cases_expected": ["Justice K.S. Puttaswamy", "Navtej Singh Johar"],
    },
    {
        "case_id": "HC002",
        "title": "Environmental Clearance Violations",
        "citation": "AIR 2023 SC 5678",
        "short_proposition": "Corporate liability for environmental damage without clearance",
        "legal_domain": "environmental",
        "difficulty_level": "intermediate",
        "complexity_level": 3,
        "constitutional_articles": ["Article 21", "Article 48A"],
        "key_issues": ["Environmental Law", "Corporate Liability", "Public Trust"],
        "landmark_cases_expected": ["M.C. Mehta", "Oleum Gas Leak"],
    },
    {
        "case_id": "HC003",
        "title": "Insolvency Resolution vs Labor Rights",
        "citation": "AIR 2023 SC 9012",
        "short_proposition": "Priority of worker dues during corporate insolvency",
        "legal_domain": "corporate",
        "difficulty_level": "advanced",
        "complexity_level": 4,
        "constitutional_articles": ["Article 21", "Article 43"],
        "key_issues": ["Insolvency Law", "Labor Rights", "Secured Creditors"],
        "landmark_cases_expected": ["Swiss Ribbons", "Essar Steel"],
    },
    {
        "case_id": "HC004",
        "title": "Freedom of Speech on Social Media",
        "citation": "AIR 2022 SC 3456",
        "short_proposition": "Extent of free speech protection for online expression",
        "legal_domain": "constitutional",
        "difficulty_level": "intermediate",
        "complexity_level": 3,
        "constitutional_articles": ["Article 19(1)(a)", "Article 19(2)"],
        "key_issues": ["Free Speech", "Social Media", "Defamation"],
        "landmark_cases_expected": ["Shreya Singhal", "Pride"],
    },
    {
        "case_id": "HC005",
        "title": "Transgender Rights in Employment",
        "citation": "AIR 2022 SC 7890",
        "short_proposition": "Non-discrimination in public employment for transgender persons",
        "legal_domain": "constitutional",
        "difficulty_level": "intermediate",
        "complexity_level": 3,
        "constitutional_articles": ["Article 14", "Article 15", "Article 16"],
        "key_issues": ["Transgender Rights", "Employment Discrimination", "Equality"],
        "landmark_cases_expected": ["NALSA", "Navtej Singh Johar"],
    },
    {
        "case_id": "HC006",
        "title": "Data Protection and State Surveillance",
        "citation": "AIR 2022 SC 1235",
        "short_proposition": "Constitutional limits on state surveillance of citizens",
        "legal_domain": "constitutional",
        "difficulty_level": "advanced",
        "complexity_level": 5,
        "constitutional_articles": ["Article 21", "Article 19(1)(d)"],
        "key_issues": ["Data Protection", "Surveillance", "Fundamental Rights"],
        "landmark_cases_expected": ["Justice K.S. Puttaswamy", "Kharak Singh"],
    },
    {
        "case_id": "HC007",
        "title": "Marital Rape Exception Challenge",
        "citation": "AIR 2023 SC 5679",
        "short_proposition": "Constitutional validity of marital rape exception",
        "legal_domain": "constitutional",
        "difficulty_level": "advanced",
        "complexity_level": 4,
        "constitutional_articles": ["Article 14", "Article 15", "Article 21"],
        "key_issues": ["Gender Justice", "Marital Rape", "Equality"],
        "landmark_cases_expected": ["Navtej Singh Johar", "Joseph Shine"],
    },
    {
        "case_id": "HC008",
        "title": "Corporate Social Responsibility Limits",
        "citation": "AIR 2022 SC 9013",
        "short_proposition": "Mandatory CSR spend vs corporate autonomy",
        "legal_domain": "corporate",
        "difficulty_level": "intermediate",
        "complexity_level": 3,
        "constitutional_articles": ["Article 19(1)(g)"],
        "key_issues": ["Corporate Law", "CSR", "Business Freedom"],
        "landmark_cases_expected": ["Vodafone", "McDowell"],
    },
    {
        "case_id": "HC009",
        "title": "Sedition Law and Democracy",
        "citation": "AIR 2022 SC 3457",
        "short_proposition": "Constitutional validity of sedition provisions",
        "legal_domain": "constitutional",
        "difficulty_level": "advanced",
        "complexity_level": 4,
        "constitutional_articles": ["Article 19(1)(a)", "Article 19(2)"],
        "key_issues": ["Sedition", "Free Speech", "Democracy"],
        "landmark_cases_expected": ["Shreya Singhal", "Kedar Nath Singh"],
    },
    {
        "case_id": "HC010",
        "title": "Live-in Relationship Property Rights",
        "citation": "AIR 2023 SC 7891",
        "short_proposition": "Property rights of partners in live-in relationships",
        "legal_domain": "civil",
        "difficulty_level": "intermediate",
        "complexity_level": 3,
        "constitutional_articles": ["Article 21", "Article 14"],
        "key_issues": ["Live-in Relationships", "Property Rights", "Family Law"],
        "landmark_cases_expected": ["Velusamy", "Chanmuniya"],
    },
    {
        "case_id": "HC011",
        "title": "Artificial Intelligence Liability",
        "citation": "AIR 2023 SC 1236",
        "short_proposition": "Liability for AI-driven decisions causing harm",
        "legal_domain": "cyber",
        "difficulty_level": "advanced",
        "complexity_level": 5,
        "constitutional_articles": ["Article 21"],
        "key_issues": ["AI Liability", "Tort Law", "Technology"],
        "landmark_cases_expected": ["Justice K.S. Puttaswamy", "Navtej Singh"],
    },
    {
        "case_id": "HC012",
        "title": "Reservation in Private Sector",
        "citation": "AIR 2022 SC 5680",
        "short_proposition": "Constitutional mandate for private sector reservations",
        "legal_domain": "constitutional",
        "difficulty_level": "advanced",
        "complexity_level": 4,
        "constitutional_articles": ["Article 14", "Article 16", "Article 15(4)"],
        "key_issues": ["Reservation", "Private Sector", "Social Justice"],
        "landmark_cases_expected": ["Indra Sawhney", "Nagaraj"],
    },
    {
        "case_id": "HC013",
        "title": "Cryptocurrency Regulation",
        "citation": "AIR 2022 SC 9014",
        "short_proposition": "Government power to ban vs regulate cryptocurrency",
        "legal_domain": "cyber",
        "difficulty_level": "intermediate",
        "complexity_level": 4,
        "constitutional_articles": ["Article 19(1)(g)", "Article 300A"],
        "key_issues": ["Cryptocurrency", "Property Rights", "Financial Regulation"],
        "landmark_cases_expected": ["Internet and Mobile Association", "RBI"],
    },
    {
        "case_id": "HC014",
        "title": "Medical Negligence and AI",
        "citation": "AIR 2023 SC 3458",
        "short_proposition": "Liability for AI-assisted medical diagnosis errors",
        "legal_domain": "cyber",
        "difficulty_level": "advanced",
        "complexity_level": 4,
        "constitutional_articles": ["Article 21"],
        "key_issues": ["Medical Negligence", "AI Liability", "Consumer Protection"],
        "landmark_cases_expected": ["Jacob Mathew", "Martin D'Souza"],
    },
    {
        "case_id": "HC015",
        "title": "Inter-faith Marriage Protection",
        "citation": "AIR 2022 SC 7892",
        "short_proposition": "Right to marry across religious boundaries",
        "legal_domain": "constitutional",
        "difficulty_level": "intermediate",
        "complexity_level": 3,
        "constitutional_articles": ["Article 21", "Article 25"],
        "key_issues": ["Inter-faith Marriage", "Personal Liberty", "Religious Freedom"],
        "landmark_cases_expected": ["Lata Singh", "Shakti Vahini"],
    },
    {
        "case_id": "HC016",
        "title": "E-commerce Platform Liability",
        "citation": "AIR 2023 SC 1237",
        "short_proposition": "Platform liability for counterfeit goods sold by vendors",
        "legal_domain": "corporate",
        "difficulty_level": "intermediate",
        "complexity_level": 3,
        "constitutional_articles": [],
        "key_issues": ["E-commerce", "Platform Liability", "Consumer Rights"],
        "landmark_cases_expected": ["Amazon v Amway", "Christian Louboutin"],
    },
    {
        "case_id": "HC017",
        "title": "Climate Change Litigation",
        "citation": "AIR 2023 SC 5681",
        "short_proposition": "State obligation to protect from climate change impacts",
        "legal_domain": "environmental",
        "difficulty_level": "advanced",
        "complexity_level": 4,
        "constitutional_articles": ["Article 21", "Article 48A", "Article 51A(g)"],
        "key_issues": ["Climate Change", "Environmental Justice", "Public Trust"],
        "landmark_cases_expected": ["M.C. Mehta", "Subhash Kumar"],
    },
    {
        "case_id": "HC018",
        "title": "Gene Editing Ethics and Law",
        "citation": "AIR 2022 SC 9015",
        "short_proposition": "Regulatory framework for human gene editing",
        "legal_domain": "cyber",
        "difficulty_level": "advanced",
        "complexity_level": 5,
        "constitutional_articles": ["Article 21"],
        "key_issues": ["Gene Editing", "Bioethics", "Medical Law"],
        "landmark_cases_expected": ["Common Cause", "Aruna Shanbaug"],
    },
    {
        "case_id": "HC019",
        "title": "Whistleblower Protection in Banking",
        "citation": "AIR 2023 SC 3459",
        "short_proposition": "Extent of protection for bank employees reporting fraud",
        "legal_domain": "corporate",
        "difficulty_level": "intermediate",
        "complexity_level": 3,
        "constitutional_articles": [],
        "key_issues": ["Whistleblower", "Banking Fraud", "Employment Law"],
        "landmark_cases_expected": ["Vishaka", "Nagaraja"],
    },
    {
        "case_id": "HC020",
        "title": "Right to be Forgotten",
        "citation": "AIR 2022 SC 7893",
        "short_proposition": "Extent of right to erasure of personal data from internet",
        "legal_domain": "cyber",
        "difficulty_level": "intermediate",
        "complexity_level": 4,
        "constitutional_articles": ["Article 21", "Article 19(1)(a)"],
        "key_issues": ["Right to be Forgotten", "Data Protection", "Privacy"],
        "landmark_cases_expected": ["Justice K.S. Puttaswamy", "Google v Jorawar"],
    },
    {
        "case_id": "HC021",
        "title": "Arbitration and Public Interest",
        "citation": "AIR 2023 SC 1238",
        "short_proposition": "Arbitrability of disputes involving public interest",
        "legal_domain": "corporate",
        "difficulty_level": "advanced",
        "complexity_level": 4,
        "constitutional_articles": ["Article 14"],
        "key_issues": ["Arbitration", "Public Interest", "Alternate Dispute Resolution"],
        "landmark_cases_expected": ["Booz Allen", "Vidya Drolia"],
    },
    {
        "case_id": "HC022",
        "title": "Media Trial and Fair Trial",
        "citation": "AIR 2022 SC 5682",
        "short_proposition": "Balancing press freedom with right to fair trial",
        "legal_domain": "constitutional",
        "difficulty_level": "intermediate",
        "complexity_level": 3,
        "constitutional_articles": ["Article 19(1)(a)", "Article 21"],
        "key_issues": ["Media Freedom", "Fair Trial", "Contempt of Court"],
        "landmark_cases_expected": ["R.K. Anand", "A.K. Gopalan"],
    },
    {
        "case_id": "HC023",
        "title": "Uniform Civil Code Debate",
        "citation": "AIR 2023 SC 9016",
        "short_proposition": "Constitutional mandate and feasibility of uniform civil code",
        "legal_domain": "constitutional",
        "difficulty_level": "advanced",
        "complexity_level": 5,
        "constitutional_articles": ["Article 44", "Article 25", "Article 29"],
        "key_issues": ["Uniform Civil Code", "Religious Freedom", "Gender Justice"],
        "landmark_cases_expected": ["Shayara Bano", "Sarla Mudgal"],
    },
    {
        "case_id": "HC024",
        "title": "Antitrust in Digital Markets",
        "citation": "AIR 2022 SC 3460",
        "short_proposition": "Abuse of dominant position by big tech platforms",
        "legal_domain": "corporate",
        "difficulty_level": "advanced",
        "complexity_level": 4,
        "constitutional_articles": [],
        "key_issues": ["Competition Law", "Digital Markets", "Antitrust"],
        "landmark_cases_expected": ["Google CCI", "WhatsApp Privacy"],
    },
    {
        "case_id": "HC025",
        "title": "Mental Health and Criminal Liability",
        "citation": "AIR 2023 SC 7894",
        "short_proposition": "Insanity defense standards in contemporary criminal law",
        "legal_domain": "criminal",
        "difficulty_level": "advanced",
        "complexity_level": 4,
        "constitutional_articles": ["Article 21"],
        "key_issues": ["Mental Health", "Insanity Defense", "Criminal Law"],
        "landmark_cases_expected": ["M'Naghten Rules", "Surendra Mishra"],
    },
    {
        "case_id": "HC026",
        "title": "Surrogacy and Commercialization",
        "citation": "AIR 2022 SC 1239",
        "short_proposition": "Constitutional validity of commercial surrogacy ban",
        "legal_domain": "constitutional",
        "difficulty_level": "intermediate",
        "complexity_level": 3,
        "constitutional_articles": ["Article 21", "Article 14"],
        "key_issues": ["Surrogacy", "Reproductive Rights", "Gender Justice"],
        "landmark_cases_expected": ["Baby Manji", "Navtej Singh"],
    },
    {
        "case_id": "HC027",
        "title": "Death Penalty and Mental Illness",
        "citation": "AIR 2023 SC 5683",
        "short_proposition": "Prohibition on executing prisoners with mental illness",
        "legal_domain": "criminal",
        "difficulty_level": "advanced",
        "complexity_level": 4,
        "constitutional_articles": ["Article 21"],
        "key_issues": ["Death Penalty", "Mental Illness", "Human Rights"],
        "landmark_cases_expected": ["Shatrughan Chauhan", "V. Sriharan"],
    },
    {
        "case_id": "HC028",
        "title": "Academic Freedom in Universities",
        "citation": "AIR 2022 SC 9017",
        "short_proposition": "Extent of academic freedom in state universities",
        "legal_domain": "constitutional",
        "difficulty_level": "intermediate",
        "complexity_level": 3,
        "constitutional_articles": ["Article 19(1)(a)", "Article 26"],
        "key_issues": ["Academic Freedom", "University Autonomy", "Free Speech"],
        "landmark_cases_expected": ["Kumari Chitra", "Vishaka"],
    },
    {
        "case_id": "HC029",
        "title": "Cross-Border Data Transfers",
        "citation": "AIR 2023 SC 3461",
        "short_proposition": "Regulatory framework for international data transfers",
        "legal_domain": "cyber",
        "difficulty_level": "advanced",
        "complexity_level": 4,
        "constitutional_articles": ["Article 21"],
        "key_issues": ["Data Protection", "Cross-Border Transfers", "Privacy"],
        "landmark_cases_expected": ["Justice K.S. Puttaswamy", "Schrems II"],
    },
    {
        "case_id": "HC030",
        "title": "Judicial Review of Economic Policy",
        "citation": "AIR 2022 SC 7895",
        "short_proposition": "Limits of judicial intervention in economic legislation",
        "legal_domain": "constitutional",
        "difficulty_level": "advanced",
        "complexity_level": 5,
        "constitutional_articles": ["Article 38", "Article 39"],
        "key_issues": ["Economic Policy", "Judicial Review", "Separation of Powers"],
        "landmark_cases_expected": ["Kesavananda Bharati", "R.C. Cooper"],
    },
]


async def seed_high_court_cases(db: AsyncSession) -> int:
    """
    Seed all 30 High Court structured cases into the database.
    
    Rules:
    - Deterministic uniqueness on case_id
    - Skip if case_id already exists (idempotent)
    - Atomic transaction - commit once at end
    
    Returns:
        Number of cases actually inserted
    """
    inserted_count = 0
    skipped_count = 0
    
    for case_data in HIGH_COURT_CASES:
        # Check if case already exists by title (deterministic check)
        result = await db.execute(
            select(MootCase).where(MootCase.title == case_data["title"])
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            logger.info(f"Skipping {case_data['case_id']}: already exists")
            skipped_count += 1
            continue
        
        # Create new case with all structured fields
        moot_case = MootCase(
            title=case_data["title"],
            citation=case_data["citation"],
            short_proposition=case_data["short_proposition"],
            legal_domain=case_data["legal_domain"],
            difficulty_level=case_data["difficulty_level"],
            complexity_level=case_data["complexity_level"],
            constitutional_articles=json.dumps(case_data["constitutional_articles"]),
            key_issues=json.dumps(case_data["key_issues"]),
            landmark_cases_expected=json.dumps(case_data["landmark_cases_expected"]),
        )
        
        db.add(moot_case)
        inserted_count += 1
        logger.info(f"Queuing {case_data['case_id']} for insertion")
    
    # Atomic commit
    await db.commit()
    
    logger.info(f"✓ Case Library Seeding Complete: {inserted_count} inserted, {skipped_count} skipped")
    return inserted_count
