"""
backend/seed/seed_ba_llb_curriculum.py
Seed BA LLB (5-Year Integrated) curriculum with complete BCI syllabus

This script seeds:
- 10 semesters
- All subjects per semester (with Major/Minor/Optional support)
- All modules per subject (in exact order from curriculum)

IDEMPOTENT: Safe to run multiple times.
"""
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import select
from backend.database import AsyncSessionLocal, init_db
from backend.orm.ba_llb_curriculum import BALLBSemester, BALLBSubject, BALLBModule

# Fix for SQLAlchemy mapper error: ensure all related models are loaded
try:
    from backend.orm.user import User
    from backend.orm.exam_session import ExamSession
except ImportError:
    pass

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


BA_LLB_CURRICULUM = {
    1: {
        "name": "Semester 1",
        "subjects": [
            {
                "name": "General and Legal English",
                "code": "SEM1_ENG_LEGAL",
                "subject_type": "core",
                "is_optional": False,
                "option_group": None,
                "is_variable": False,
                "modules": [
                    "Unit 1: Introduction to Language",
                    "Unit 2: Structure, Usage and Vocabulary",
                    "Unit 3: Legal Language",
                    "Unit 4: Reading, Speaking and Listening Skills",
                    "Unit 5: Oral Presentation Strategies",
                ]
            },
            {
                "name": "Fundamental Principles of Political Science",
                "code": "SEM1_POL_SCI",
                "subject_type": "major",
                "is_optional": False,
                "option_group": None,
                "is_variable": True,
                "modules": [
                    "Unit 1: Introduction to Political Science",
                    "Unit 2: Political Concepts",
                    "Unit 3: Organs of Government",
                    "Unit 4: Political Ideologies",
                ]
            },
            {
                "name": "Sociology – I (Legal Sociology)",
                "code": "SEM1_SOC_LEGAL",
                "subject_type": "minor_i",
                "is_optional": False,
                "option_group": None,
                "is_variable": True,
                "modules": [
                    "Unit 1: Introduction to Sociology",
                    "Unit 2: Legal Sociology and Social Control",
                    "Unit 3: Family and Community",
                    "Unit 4: Social Disorganization and Problems",
                ]
            },
            {
                "name": "Indian History – Part I",
                "code": "SEM1_HISTORY1",
                "subject_type": "minor_ii",
                "is_optional": False,
                "option_group": None,
                "is_variable": True,
                "modules": [
                    "Unit 1: Pre-Historic and Ancient India",
                    "Unit 2: Early Medieval India",
                    "Unit 3: Later Medieval India",
                    "Unit 4: Mughal Era",
                ]
            },
            {
                "name": "Law of Torts including Motor Vehicle Accident and Consumer Protection Laws",
                "code": "SEM1_TORTS_MV_CP",
                "subject_type": "core",
                "is_optional": False,
                "option_group": None,
                "is_variable": False,
                "modules": [
                    "Unit 1: Introduction to Torts",
                    "Unit 2: Specific Torts",
                    "Unit 3: Vicarious Liability and Remedies",
                    "Unit 4: Consumer Protection and MV Act",
                ]
            },
            {
                "name": "General Principles and Theories of Contract (Sections 1–75)",
                "code": "SEM1_CONTRACT1",
                "subject_type": "core",
                "is_optional": False,
                "option_group": None,
                "is_variable": False,
                "modules": [
                    "Unit 1: Introduction and Formation of Contract",
                    "Unit 2: Capacity and Validity of Contract",
                    "Unit 3: Discharge of Contract",
                    "Unit 4: Quasi Contract and Damages",
                ]
            },
            {
                "name": "Universal Human Values and Professional Ethics (Foundation Course)",
                "code": "SEM1_VALUES_ETHICS",
                "subject_type": "foundation",
                "is_optional": False,
                "option_group": None,
                "is_variable": False,
                "modules": [
                    "Introduction to Value Education",
                    "Harmony in Human Being",
                    "Harmony in Family and Society",
                    "Harmony in Nature and Existence",
                    "Ethical Implications in Profession",
                ]
            },
        ]
    },
    2: {
        "name": "Semester 2",
        "subjects": [
            {
                "name": "Language Paper (e.g., Hindi / Regional Language)",
                "code": "SEM2_LANG",
                "subject_type": "core",
                "is_optional": False,
                "option_group": None,
                "is_variable": False,
                "modules": [
                    "Applied Grammar and Syntax",
                    "Translation of Legal Passages (English to Vernacular and vice-versa)",
                    "Official Correspondence and Drafting",
                    "Legal Terminology in Vernacular Language",
                    "Literature: Selected Prose and Poetry (Prescribed by University)",
                    "Essay Writing on Socio-Legal Issues",
                ]
            },
            {
                "name": "Major–II (Political Science: Political Organization)",
                "code": "SEM2_POL_ORG",
                "subject_type": "major",
                "is_optional": False,
                "option_group": None,
                "is_variable": True,
                "modules": [
                    "Forms of Government: Unitary and Federal",
                    "Parliamentary and Presidential Systems",
                    "Organs of Government: Legislature (Unicameral/Bicameral)",
                    "Organs of Government: Executive and its Types",
                    "Organs of Government: Judiciary and Judicial Independence",
                    "Representation: Electorates and Election Methods",
                    "Public Opinion and Media",
                ]
            },
            {
                "name": "Minor–I (Paper 2: Indian Society)",
                "code": "SEM2_SOC_INDIAN",
                "subject_type": "minor_i",
                "is_optional": False,
                "option_group": None,
                "is_variable": True,
                "modules": [
                    "Features of Indian Society: Unity in Diversity",
                    "The Caste System: Traditional vs. Contemporary",
                    "Tribal Societies in India: Problems and Integration",
                    "Rural and Urban Social Structure",
                    "Religion in India: Secularism and Communalism",
                    "Social Problems: Poverty, Unemployment, and Corruption",
                    "Status of Women in Indian Society",
                ]
            },
            {
                "name": "Minor–II (Paper 2: Economics – I)",
                "code": "SEM2_ECO1",
                "subject_type": "minor_ii",
                "is_optional": False,
                "option_group": None,
                "is_variable": True,
                "modules": [
                    "Introduction to Economics and Microeconomics",
                    "Theory of Demand and Supply",
                    "Consumer Behavior and Elasticity",
                    "Factors of Production: Land, Labor, Capital, and Organization",
                    "Market Structures: Perfect Competition, Monopoly, and Oligopoly",
                    "National Income: Concepts and Measurement",
                    "Introduction to Money and Banking",
                ]
            },
            {
                "name": "Law of Torts",
                "code": "SEM2_TORTS",
                "subject_type": "core",
                "is_optional": False,
                "option_group": None,
                "is_variable": False,
                "modules": [
                    "Evolution and Definition of Tortious Liability",
                    "General Defenses in Torts",
                    "Vicarious Liability and State Liability",
                    "Specific Torts: Negligence, Nuisance, and Defamation",
                    "Torts against Person and Property: Assault, Battery, Trespass",
                    "Strict Liability and Absolute Liability (Rylands vs. Fletcher / MC Mehta)",
                    "Consumer Protection Act, 2019: Authorities and Remedies",
                    "Motor Vehicles Act: Liability and Insurance",
                ]
            },
        ]
    },
    3: {
        "name": "Semester 3",
        "subjects": [
            {
                "name": "Major–III (Political Science: Indian Political Thought)",
                "code": "SEM3_POL_INDIAN",
                "subject_type": "major",
                "is_optional": False,
                "option_group": None,
                "is_variable": True,
                "modules": [
                    "Ancient Indian Thought: Manu and Kautilya",
                    "Buddhist and Jain Political Perspectives",
                    "Raja Ram Mohan Roy and the Indian Renaissance",
                    "Political Thought of M.K. Gandhi: Satyagraha and Sarvodaya",
                    "B.R. Ambedkar: Social Justice and Constitutionalism",
                    "Socialist Thought: J.P. Narayan and Ram Manohar Lohia",
                    "Cultural Nationalism: V.D. Savarkar and Iqbal",
                ]
            },
            {
                "name": "Major–IV (Political Science: Western Political Thought)",
                "code": "SEM3_POL_WESTERN",
                "subject_type": "major",
                "is_optional": False,
                "option_group": None,
                "is_variable": True,
                "modules": [
                    "Ancient Greek Thought: Plato (Republic) and Aristotle (Politics)",
                    "Medieval Thought: St. Thomas Aquinas and Machiavelli",
                    "Social Contract Theory: Hobbes, Locke, and Rousseau",
                    "Utilitarianism: Jeremy Bentham and J.S. Mill",
                    "Idealism: Hegel and Green",
                    "Scientific Socialism: Karl Marx and Friedrich Engels",
                    "Modern Trends: Harold Laski and John Rawls",
                ]
            },
            {
                "name": "Minor–I (Paper 3: Sociological Thoughts)",
                "code": "SEM3_SOC_THOUGHTS",
                "subject_type": "minor_i",
                "is_optional": False,
                "option_group": None,
                "is_variable": True,
                "modules": [
                    "Emergence of Sociology as a Discipline",
                    "Auguste Comte: Positivism and Law of Three Stages",
                    "Herbert Spencer: Social Darwinism and Organic Analogy",
                    "Emile Durkheim: Social Facts, Suicide, and Division of Labor",
                    "Max Weber: Social Action, Bureaucracy, and Protestant Ethics",
                    "Karl Marx: Historical Materialism and Class Struggle",
                    "Talcott Parsons and Robert Merton: Functionalism",
                ]
            },
            {
                "name": "Minor–II (Paper 3: Economics – II)",
                "code": "SEM3_ECO2",
                "subject_type": "minor_ii",
                "is_optional": False,
                "option_group": None,
                "is_variable": True,
                "modules": [
                    "Indian Economy: Nature and Characteristics",
                    "Agriculture: Importance, Productivity, and Land Reforms",
                    "Industrial Sector: Public vs. Private and MSMEs",
                    "Public Finance: Revenue, Expenditure, and Budgeting",
                    "Planning in India: NITI Aayog and Five-Year Plans",
                    "Foreign Trade: Balance of Payments and WTO",
                    "Poverty and Inequality in India",
                ]
            },
            {
                "name": "Constitutional Law I",
                "code": "SEM3_CONST1",
                "subject_type": "core",
                "is_optional": False,
                "option_group": None,
                "is_variable": False,
                "modules": [
                    "Historical Background and Preamble",
                    "Citizenship and the Concept of 'State' (Art. 12)",
                    "Right to Equality (Art. 14-18)",
                    "Right to Freedom (Art. 19-22)",
                    "Right against Exploitation and Freedom of Religion",
                    "Cultural, Educational Rights, and Constitutional Remedies (Art. 32)",
                    "Directive Principles of State Policy and Fundamental Duties",
                ]
            },
        ]
    },
    4: {
        "name": "Semester 4",
        "subjects": [
            {
                "name": "Major–V (Political Science: International Relations)",
                "code": "SEM4_POL_IR",
                "subject_type": "major",
                "is_optional": False,
                "option_group": None,
                "is_variable": True,
                "modules": [
                    "Nature, Scope, and Importance of International Relations",
                    "Theories: Idealism, Realism, and Neo-Realism",
                    "National Power and National Interest",
                    "Diplomacy: Types, Functions, and Privileges",
                    "The United Nations: Structure and Role in Peace-keeping",
                    "Cold War and Post-Cold War Global Order",
                    "Indian Foreign Policy: Principles and Challenges",
                ]
            },
            {
                "name": "Major–VI (Political Science: Public Administration)",
                "code": "SEM4_POL_ADMIN",
                "subject_type": "major",
                "is_optional": False,
                "option_group": None,
                "is_variable": True,
                "modules": [
                    "Public Administration: Meaning, Scope, and Evolution",
                    "Theories of Organization: Scientific and Human Relations",
                    "Principles of Organization: Hierarchy, Span of Control, and Unity of Command",
                    "Personnel Administration: Recruitment, Training, and Promotion",
                    "Financial Administration: Budgetary Process in India",
                    "Accountability and Control: Legislative, Executive, and Judicial",
                    "Decentralization: Panchayati Raj Institutions",
                ]
            },
            {
                "name": "Constitutional Law II",
                "code": "SEM4_CONST2",
                "subject_type": "core",
                "is_optional": False,
                "option_group": None,
                "is_variable": False,
                "modules": [
                    "The Union and State Executive",
                    "The Union and State Legislature",
                    "The Union and State Judiciary: Jurisdiction and Powers",
                    "Federalism: Legislative, Administrative, and Financial Relations",
                    "Freedom of Trade, Commerce, and Intercourse",
                    "Emergency Provisions (Art. 352, 356, 360)",
                    "Amendment of the Constitution and Basic Structure Doctrine",
                ]
            },
            {
                "name": "Law of Crimes I (General Principles)",
                "code": "SEM4_CRIMES1",
                "subject_type": "core",
                "is_optional": False,
                "option_group": None,
                "is_variable": False,
                "modules": [
                    "Nature of Crime and Elements (Actus Reus/Mens Rea)",
                    "Stages of Crime and Inchoate Crimes",
                    "General Exceptions: Mistake, Accident, Infancy, Insanity",
                    "Right of Private Defense",
                    "Abetment and Criminal Conspiracy",
                    "Types of Punishments under IPC",
                    "Offences against the State and Public Tranquility",
                ]
            },
            {
                "name": "Contract I (Law of General Contract)",
                "code": "SEM4_CONTRACT1",
                "subject_type": "core",
                "is_optional": False,
                "option_group": None,
                "is_variable": False,
                "modules": [
                    "Formation of Contract: Proposal and Acceptance",
                    "Consideration and Capacity to Contract",
                    "Free Consent: Coercion, Undue Influence, Fraud, Mistake",
                    "Void Agreements and Legality of Object",
                    "Discharge of Contract and Doctrine of Frustration",
                    "Remedies for Breach: Damages and Quantum Meruit",
                    "Specific Relief Act: Recovery, Injunctions, and Declaratory Decrees",
                ]
            },
        ]
    },
    5: {
        "name": "Semester 5",
        "subjects": [
            {
                "name": "Labour Law I",
                "code": "SEM5_LABOUR1",
                "subject_type": "core",
                "is_optional": False,
                "option_group": None,
                "is_variable": False,
                "modules": [
                    "Trade Unions Act: Registration and Immunities",
                    "Industrial Disputes Act: Authorities and Dispute Settlement",
                    "Strikes, Lockouts, Lay-off, and Retrenchment",
                    "Standing Orders: Industrial Employment (SO) Act",
                    "Disciplinary Proceedings and Domestic Enquiry",
                    "Collective Bargaining and Workers' Participation",
                ]
            },
            {
                "name": "Jurisprudence",
                "code": "SEM5_JURIS",
                "subject_type": "core",
                "is_optional": False,
                "option_group": None,
                "is_variable": False,
                "modules": [
                    "Nature and Value of Jurisprudence",
                    "Schools: Natural Law and Analytical Positivism",
                    "Schools: Historical, Sociological, and Realist",
                    "Legal Rights and Duties: Classification and Correlation",
                    "Ownership and Possession: Concepts and Kinds",
                    "Legal Personality: Status of Unborn, Dead, and Corporations",
                    "Liability: Negligence, Strict, and Vicarious",
                ]
            },
            {
                "name": "Family Law I",
                "code": "SEM5_FAMILY1",
                "subject_type": "core",
                "is_optional": False,
                "option_group": None,
                "is_variable": False,
                "modules": [
                    "Sources and Schools of Hindu and Muslim Law",
                    "Marriage under Hindu Law: Conditions and Ceremonies",
                    "Matrimonial Remedies: Divorce, Nullity, and Restitution",
                    "Nikah: Essential Requirements and Kinds of Dower (Mahr)",
                    "Dissolution of Muslim Marriage: Talaq and Dissolution Act 1939",
                    "Maintenance: Hindu, Muslim, and Sec. 125 CrPC",
                    "Guardianship and Adoption Laws",
                ]
            },
            {
                "name": "Contract II (Specific Contracts)",
                "code": "SEM5_CONTRACT2",
                "subject_type": "core",
                "is_optional": False,
                "option_group": None,
                "is_variable": False,
                "modules": [
                    "Contract of Indemnity and Guarantee",
                    "Bailment and Pledge",
                    "Contract of Agency: Creation and Termination",
                    "Sale of Goods: Conditions and Warranties",
                    "Rights of Unpaid Seller",
                    "Partnership Act: Formation and Dissolution",
                    "Limited Liability Partnership (LLP) Overview",
                ]
            },
            {
                "name": "Administrative Law",
                "code": "SEM5_ADMIN",
                "subject_type": "core",
                "is_optional": False,
                "option_group": None,
                "is_variable": False,
                "modules": [
                    "Evolution, Definition, and Rule of Law",
                    "Separation of Powers",
                    "Delegated Legislation: Control and Safeguards",
                    "Principles of Natural Justice: Audi Alteram Partem and Bias",
                    "Administrative Discretion and Judicial Review",
                    "Administrative Tribunals",
                    "Ombudsman: Lokpal and Lokayukta",
                ]
            },
        ]
    },
    6: {
        "name": "Semester 6",
        "subjects": [
            {
                "name": "Labour Law II",
                "code": "SEM6_LABOUR2",
                "subject_type": "core",
                "is_optional": False,
                "option_group": None,
                "is_variable": False,
                "modules": [
                    "Factories Act: Health, Safety, and Welfare",
                    "Employee's Compensation Act: Employer's Liability",
                    "Minimum Wages Act and Payment of Wages Act",
                    "Employee State Insurance (ESI) Act",
                    "Employee's Provident Fund (EPF) Act",
                    "Payment of Bonus and Payment of Gratuity",
                    "Maternity Benefit and Equal Remuneration Acts",
                ]
            },
            {
                "name": "Company Law",
                "code": "SEM6_COMPANY",
                "subject_type": "core",
                "is_optional": False,
                "option_group": None,
                "is_variable": False,
                "modules": [
                    "Corporate Personality and Lifting the Veil",
                    "Formation: Promotion and Incorporation",
                    "Memorandum and Articles of Association",
                    "Prospectus, Shares, and Debentures",
                    "Directors: Appointment, Duties, and Liabilities",
                    "Company Meetings and Resolutions",
                    "Minority Rights and Prevention of Oppression/Mismanagement",
                    "Winding Up of Companies",
                ]
            },
            {
                "name": "Property Law",
                "code": "SEM6_PROPERTY",
                "subject_type": "core",
                "is_optional": False,
                "option_group": None,
                "is_variable": False,
                "modules": [
                    "Concept of Property and General Principles of Transfer",
                    "Transfer by Non-owners and Part Performance",
                    "Sale of Immovable Property",
                    "Mortgages: Rights and Liabilities of Parties",
                    "Leases of Immovable Property",
                    "Exchanges and Gifts",
                    "Actionable Claims and Easements Act",
                ]
            },
            {
                "name": "Family Law II",
                "code": "SEM6_FAMILY2",
                "subject_type": "core",
                "is_optional": False,
                "option_group": None,
                "is_variable": False,
                "modules": [
                    "Hindu Undivided Family and Coparcenary",
                    "Partition and Re-union",
                    "Hindu Succession Act, 1956 (General Principles)",
                    "Successions to Property of Hindu Male and Female",
                    "Muslim Law of Inheritance (Hanafi and Shia)",
                    "Wills (Wasiyat) and Gifts (Hiba)",
                    "Wakf and Pre-emption",
                ]
            },
        ]
    },
    7: {
        "name": "Semester 7",
        "subjects": [
            {
                "name": "Public International Law",
                "code": "SEM7_INTL_LAW",
                "subject_type": "core",
                "is_optional": False,
                "option_group": None,
                "is_variable": False,
                "modules": [
                    "Nature, Basis, and Sources of International Law",
                    "Relationship between International and Municipal Law",
                    "Subjects of International Law and Recognition",
                    "State Territory and Succession",
                    "Extradition and Asylum",
                    "Law of Treaties",
                    "Law of the Sea: Maritime Zones",
                ]
            },
            {
                "name": "Law of Taxation",
                "code": "SEM7_TAX",
                "subject_type": "core",
                "is_optional": False,
                "option_group": None,
                "is_variable": False,
                "modules": [
                    "Constitutional Provisions regarding Taxation",
                    "Income Tax: Definitions and Basis of Charge",
                    "Heads of Income: Salary, House Property, Business/Profession",
                    "Capital Gains and Other Sources",
                    "Deductions and Exemptions",
                    "Assessment Procedure and Income Tax Authorities",
                    "Introduction to Goods and Services Tax (GST)",
                ]
            },
            {
                "name": "Criminal Law II (CrPC)",
                "code": "SEM7_CRPC",
                "subject_type": "core",
                "is_optional": False,
                "option_group": None,
                "is_variable": False,
                "modules": [
                    "Constitution and Powers of Criminal Courts",
                    "Arrest of Persons and Rights of Arrestee",
                    "Summons and Warrants: Compelling Appearance/Production",
                    "Information to Police: FIR and Investigation Powers",
                    "Maintenance of Public Order and Tranquility",
                    "Framing of Charges and Trials (Session, Warrant, Summary)",
                    "Bail, Appeals, Reference, and Revision",
                ]
            },
            {
                "name": "Clinical Course I: Professional Ethics & Accounting",
                "code": "SEM7_CLINICAL1",
                "subject_type": "clinical",
                "is_optional": False,
                "option_group": None,
                "is_variable": False,
                "modules": [
                    "History and Development of Legal Profession in India",
                    "Bar Council of India: Structure and Functions",
                    "Seven Lamps of Advocacy",
                    "Professional Misconduct and Disciplinary Proceedings",
                    "Contempt of Court Act",
                    "Accountancy for Lawyers: Bar-Bench Relations",
                ]
            },
        ]
    },
    8: {
        "name": "Semester 8",
        "subjects": [
            {
                "name": "Law of Evidence",
                "code": "SEM8_EVIDENCE",
                "subject_type": "core",
                "is_optional": False,
                "option_group": None,
                "is_variable": False,
                "modules": [
                    "Central Conceptions: Fact, Evidence, and Proof",
                    "Relevancy of Facts and Res Gestae",
                    "Admissions and Confessions",
                    "Dying Declarations and Expert Opinion",
                    "Oral and Documentary Evidence: Primary and Secondary",
                    "Burden of Proof and Presumptions",
                    "Estoppel and Examination of Witnesses",
                ]
            },
            {
                "name": "Optional I (Human Rights)",
                "code": "SEM8_OPT_HR",
                "subject_type": "optional",
                "is_optional": True,
                "option_group": "Optional I",
                "is_variable": False,
                "modules": [
                    "Concept, History, and Generations of Human Rights",
                    "UN Charter and Universal Declaration of Human Rights (UDHR)",
                    "International Covenants: ICCPR and ICESCR",
                    "Protection of Human Rights Act, 1993 (NHRC/SHRC)",
                    "Rights of Vulnerable Groups: Women, Children, and Minorities",
                    "Regional Systems: European and American Perspectives",
                ]
            },
            {
                "name": "Optional II (Banking Law)",
                "code": "SEM8_OPT_BANK",
                "subject_type": "optional",
                "is_optional": True,
                "option_group": "Optional II",
                "is_variable": False,
                "modules": [
                    "Evolution of Banking in India and RBI Act",
                    "Banker-Customer Relationship",
                    "Negotiable Instruments: Cheques, Bills, and Notes",
                    "Dishonor of Cheques: Sec. 138-142 NI Act",
                    "Lending and Securities: Guarantees and Hypothecation",
                    "SARFAESI Act and Debt Recovery Tribunals",
                ]
            },
            {
                "name": "Clinical Course II: ADR",
                "code": "SEM8_CLINICAL2",
                "subject_type": "clinical",
                "is_optional": False,
                "option_group": None,
                "is_variable": False,
                "modules": [
                    "ADR: Evolution, Advantages, and Kinds",
                    "Arbitration and Conciliation Act: General Provisions",
                    "Appointment of Arbitrators and Conduct of Proceedings",
                    "Arbitral Awards and Recourse against Awards",
                    "Mediation and Conciliation Rules",
                    "Lok Adalats and Permanent Lok Adalats",
                ]
            },
        ]
    },
    9: {
        "name": "Semester 9",
        "subjects": [
            {
                "name": "Civil Procedure Code & Limitation Act",
                "code": "SEM9_CPC",
                "subject_type": "core",
                "is_optional": False,
                "option_group": None,
                "is_variable": False,
                "modules": [
                    "Definitions, Jurisdiction, and Res Judicata",
                    "Institution of Suit: Parties and Pleadings",
                    "Summons, Appearance, and Consequences of Non-appearance",
                    "Interim Orders: Injunctions, Commissions, Arrest/Attachment",
                    "Trial and Judgment: Decree and Orders",
                    "Execution of Decrees",
                    "Appeals, Reference, Review, and Revision",
                    "Limitation Act: General Principles and Computation",
                ]
            },
            {
                "name": "Optional III (IPR)",
                "code": "SEM9_OPT_IPR",
                "subject_type": "optional",
                "is_optional": True,
                "option_group": "Optional III",
                "is_variable": False,
                "modules": [
                    "Introduction to Intellectual Property",
                    "Patent Law: Criteria, Procedure, and Infringement",
                    "Copyright Law: Ownership, Rights, and Fair Dealing",
                    "Trademarks: Registration and Passing Off",
                    "Industrial Designs and Geographical Indications",
                    "IPR in the Digital Age: Software and Bio-piracy",
                ]
            },
            {
                "name": "Optional IV (Interpretation of Statutes)",
                "code": "SEM9_OPT_IOS",
                "subject_type": "optional",
                "is_optional": True,
                "option_group": "Optional IV",
                "is_variable": False,
                "modules": [
                    "Meaning and Purpose of Interpretation",
                    "Primary Rules: Literal, Golden, and Mischief Rules",
                    "Subsidiary Rules: Ejusdem Generis and Noscitur a Sociis",
                    "Internal Aids to Interpretation",
                    "External Aids to Interpretation",
                    "Interpretation of Constitution and Penal Statutes",
                ]
            },
            {
                "name": "Clinical Course III: Drafting, Pleading & Conveyancing",
                "code": "SEM9_CLINICAL3",
                "subject_type": "clinical",
                "is_optional": False,
                "option_group": None,
                "is_variable": False,
                "modules": [
                    "General Principles of Pleading",
                    "Drafting of Plaint and Written Statement",
                    "Drafting of Criminal Complaint and Bail Application",
                    "Drafting of Writ Petitions",
                    "Conveyancing: Sale Deed, Mortgage Deed, and Lease Deed",
                    "Drafting of Will, Power of Attorney, and Gift Deed",
                ]
            },
        ]
    },
    10: {
        "name": "Semester 10",
        "subjects": [
            {
                "name": "Environmental Law",
                "code": "SEM10_ENV",
                "subject_type": "core",
                "is_optional": False,
                "option_group": None,
                "is_variable": False,
                "modules": [
                    "Constitutional Provisions and Environmental Policy",
                    "Common Law Remedies and Public Trust Doctrine",
                    "Water (Prevention and Control of Pollution) Act",
                    "Air (Prevention and Control of Pollution) Act",
                    "Environment Protection Act, 1986",
                    "Wild Life Protection and Forest Conservation",
                    "International Environmental Law: Stockholm and Rio",
                ]
            },
            {
                "name": "Optional V (White Collar Crimes)",
                "code": "SEM10_OPT_WCC",
                "subject_type": "optional",
                "is_optional": True,
                "option_group": "Optional V",
                "is_variable": False,
                "modules": [
                    "Concept, Causes, and Sutherland's Theory",
                    "Corruption in Public Life: PC Act, 1988",
                    "Corporate Crimes: Fraud, Falsification of Accounts",
                    "Money Laundering and FEMA Violations",
                    "Cyber Crimes: IT Act Overview",
                    "Adulteration of Food and Drugs",
                ]
            },
            {
                "name": "Optional VI (Land Laws)",
                "code": "SEM10_OPT_LAND",
                "subject_type": "optional",
                "is_optional": True,
                "option_group": "Optional VI",
                "is_variable": False,
                "modules": [
                    "Land Reforms in India: Objectives and Impact",
                    "Constitutional Protection to Land Laws",
                    "Right to Fair Compensation (LARR Act, 2013)",
                    "State Specific Land Revenue Code (e.g., KLR Act)",
                    "Tenancy Laws: Fixity of Tenure and Rent Control",
                    "Land Records and Mutation",
                ]
            },
            {
                "name": "Clinical Course IV: Moot Court & Internship",
                "code": "SEM10_CLINICAL4",
                "subject_type": "clinical",
                "is_optional": False,
                "option_group": None,
                "is_variable": False,
                "modules": [
                    "Moot Court: Preparation and Presentation",
                    "Court Visit: Observation of Civil Trials",
                    "Court Visit: Observation of Criminal Trials",
                    "Chamber/Office Visit: Lawyer's Interview Techniques",
                    "Internship Diary and Viva Voce",
                ]
            },
        ]
    },
}


async def seed_ba_llb_curriculum():
    """Seed the complete BA LLB curriculum (idempotent)."""
    async with AsyncSessionLocal() as session:
        try:
            logger.info("=" * 70)
            logger.info("SEEDING BA LLB (5-YEAR INTEGRATED) CURRICULUM")
            logger.info("=" * 70)
            
            total_semesters = 0
            total_subjects = 0
            total_modules = 0
            
            for semester_num, semester_data in BA_LLB_CURRICULUM.items():
                stmt = select(BALLBSemester).where(
                    BALLBSemester.semester_number == semester_num
                )
                result = await session.execute(stmt)
                semester = result.scalar_one_or_none()
                
                if not semester:
                    semester = BALLBSemester(
                        semester_number=semester_num,
                        name=semester_data["name"]
                    )
                    session.add(semester)
                    await session.flush()
                    total_semesters += 1
                    logger.info(f"✓ Created {semester_data['name']}")
                else:
                    logger.info(f"⟳ Updating {semester_data['name']}")
                    # Optional: Clear existing subjects for this semester to ensure clean seed
                    # Only doing this if it's Semester 1 as per specific request
                    if semester_num == 1:
                        from sqlalchemy import delete
                        await session.execute(delete(BALLBSubject).where(BALLBSubject.semester_id == semester.id))
                        await session.flush()
                        logger.info(f"  ⚠ Cleared existing subjects for Semester 1 for clean update")
                
                for subj_order, subj_data in enumerate(semester_data["subjects"], 1):
                    stmt = select(BALLBSubject).where(
                        BALLBSubject.semester_id == semester.id,
                        BALLBSubject.code == subj_data["code"]
                    )
                    result = await session.execute(stmt)
                    subject = result.scalar_one_or_none()
                    
                    if not subject:
                        subject = BALLBSubject(
                            semester_id=semester.id,
                            name=subj_data["name"],
                            code=subj_data["code"],
                            subject_type=subj_data["subject_type"],
                            is_optional=subj_data["is_optional"],
                            option_group=subj_data["option_group"],
                            is_variable=subj_data["is_variable"],
                            display_order=subj_order
                        )
                        session.add(subject)
                        await session.flush()
                        total_subjects += 1
                        logger.info(f"  ✓ Created subject: {subj_data['name'][:50]}...")
                    else:
                        # Update existing subject
                        subject.name = subj_data["name"]
                        subject.subject_type = subj_data["subject_type"]
                        subject.is_optional = subj_data["is_optional"]
                        subject.option_group = subj_data["option_group"]
                        subject.is_variable = subj_data["is_variable"]
                        subject.display_order = subj_order
                        
                        # Clear modules to re-seed in correct order
                        from sqlalchemy import delete
                        await session.execute(delete(BALLBModule).where(BALLBModule.subject_id == subject.id))
                        await session.flush()
                        logger.info(f"  ⟳ Updated subject and cleared modules: {subj_data['name'][:50]}...")
                    
                    for mod_order, mod_title in enumerate(subj_data["modules"], 1):
                        module = BALLBModule(
                            subject_id=subject.id,
                            title=mod_title,
                            sequence_order=mod_order
                        )
                        session.add(module)
                        total_modules += 1
            
            await session.commit()
            
            logger.info("")
            logger.info("=" * 70)
            logger.info("SEED SUMMARY")
            logger.info("=" * 70)
            logger.info(f"Semesters created: {total_semesters}")
            logger.info(f"Subjects created: {total_subjects}")
            logger.info(f"Modules created: {total_modules}")
            
            stmt = select(BALLBSemester)
            result = await session.execute(stmt)
            semesters = result.scalars().all()
            
            logger.info("")
            logger.info("CURRICULUM VERIFICATION:")
            for sem in sorted(semesters, key=lambda s: s.semester_number):
                stmt = select(BALLBSubject).where(BALLBSubject.semester_id == sem.id)
                result = await session.execute(stmt)
                subjects = result.scalars().all()
                
                subject_module_counts = []
                for subj in subjects:
                    stmt = select(BALLBModule).where(BALLBModule.subject_id == subj.id)
                    result = await session.execute(stmt)
                    modules = result.scalars().all()
                    subject_module_counts.append(f"{subj.name[:30]}({len(modules)} modules)")
                
                logger.info(f"  Semester {sem.semester_number}: {len(subjects)} subjects")
                for smc in subject_module_counts:
                    logger.info(f"    - {smc}")
            
        except Exception as e:
            logger.error(f"❌ Error seeding BA LLB curriculum: {str(e)}")
            await session.rollback()
            raise


async def main():
    """Main entry point."""
    await init_db()
    await seed_ba_llb_curriculum()
    logger.info("\n✅ BA LLB curriculum seeding complete")


if __name__ == "__main__":
    asyncio.run(main())
