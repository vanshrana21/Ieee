"""India Legal Knowledge Base — Phase 1 MVP. Contains 15 landmark Supreme Court cases covering core Indian moot court topics. All citations in SCC format. Zero foreign cases."""
from typing import List, Dict, Optional
import re


class LandmarkCase:
    """Represents a landmark Supreme Court case of India."""
    
    def __init__(self, name: str, citation: str, year: int, key_principle: str, must_cite_for: List[str]):
        self.name = name
        self.citation = citation
        self.year = year
        self.key_principle = key_principle
        self.must_cite_for = must_cite_for
    
    def matches_argument(self, argument: str) -> bool:
        """Returns True if any token from must_cite_for appears in argument.lower()."""
        argument_lower = argument.lower()
        for keyword in self.must_cite_for:
            if keyword.lower() in argument_lower:
                return True
        return False
    
    def __repr__(self) -> str:
        return f"<LandmarkCase: {self.name}, {self.citation}>"


class StatuteProvision:
    """Represents a statute provision with act, sections, and optional key case."""
    
    def __init__(self, act: str, sections: List[str], key_case: Optional[str] = None):
        self.act = act
        self.sections = sections
        self.key_case = key_case


# Landmark Cases Database - 15 cases covering core Indian moot court topics
LANDMARK_CASES: Dict[str, List[LandmarkCase]] = {
    "privacy": [
        LandmarkCase(
            name="Justice K.S. Puttaswamy (Retd.) v. Union of India",
            citation="(2017) 10 SCC 1",
            year=2017,
            key_principle="Right to privacy fundamental under Article 21; proportionality test required",
            must_cite_for=["privacy", "personal data", "data protection", "aadhaar", "surveillance", "biometric"]
        ),
        LandmarkCase(
            name="Anuradha Bhasin v. Union of India",
            citation="(2020) 3 SCC 637",
            year=2020,
            key_principle="Internet shutdowns must satisfy proportionality test; freedom of speech extends to internet",
            must_cite_for=["internet shutdown", "digital rights", "online speech", "network suspension"]
        ),
    ],
    "free_speech": [
        LandmarkCase(
            name="Shreya Singhal v. Union of India",
            citation="(2015) 5 SCC 1",
            year=2015,
            key_principle="Struck down Section 66A IT Act for vagueness; reasonable restrictions under Article 19(2) must be narrowly tailored",
            must_cite_for=["social media", "online speech", "section 66a", "it act", "hate speech online"]
        ),
        LandmarkCase(
            name="Ramji Lal Modi v. State of Uttar Pradesh",
            citation="(1957) SCR 874",
            year=1957,
            key_principle="Section 295A IPC constitutional; requires 'deliberate and malicious intention' to outrage religious feelings",
            must_cite_for=["religious sentiments", "section 295a", "blasphemy", "hurting religious feelings"]
        ),
    ],
    "constitutional_law": [
        LandmarkCase(
            name="Kesavananda Bharati v. State of Kerala",
            citation="(1973) 4 SCC 225",
            year=1973,
            key_principle="Basic Structure Doctrine; Parliament cannot amend basic structure of Constitution",
            must_cite_for=["constitutional amendment", "basic structure", "parliament power", "article 368"]
        ),
        LandmarkCase(
            name="Maneka Gandhi v. Union of India",
            citation="(1978) 1 SCC 248",
            year=1978,
            key_principle="'Procedure established by law' under Article 21 must be fair, just and reasonable",
            must_cite_for=["due process", "article 21", "procedure established by law", "fair procedure"]
        ),
    ],
    "bail": [
        LandmarkCase(
            name="State of Rajasthan v. Balchand",
            citation="(1977) 2 SCC 52",
            year=1977,
            key_principle="Bail is rule, jail exception; presumption of innocence fundamental",
            must_cite_for=["bail", "grant bail", "custody", "jail", "pre-trial detention"]
        ),
        LandmarkCase(
            name="Gurbaksh Singh Sibbia v. State of Punjab",
            citation="(1980) 2 SCC 565",
            year=1980,
            key_principle="Anticipatory bail under Section 438 CrPC available even before FIR",
            must_cite_for=["anticipatory bail", "section 438", "pre-arrest bail", "fear of arrest"]
        ),
    ],
    "defamation": [
        LandmarkCase(
            name="Subramanian Swamy v. Union of India",
            citation="(2016) 7 SCC 221",
            year=2016,
            key_principle="Criminal defamation (Sections 499/500 IPC) constitutional; reputation integral to dignity under Article 21",
            must_cite_for=["defamation", "reputation", "section 499", "section 500"]
        ),
    ],
    "lgbtq_rights": [
        LandmarkCase(
            name="Navtej Singh Johar v. Union of India",
            citation="(2018) 10 SCC 1",
            year=2018,
            key_principle="Section 377 IPC unconstitutional for consensual same-sex relations; sexual orientation integral to privacy under Article 21",
            must_cite_for=["lgbtq", "section 377", "sexual orientation", "homosexuality", "same sex"]
        ),
    ],
    "gender_equality": [
        LandmarkCase(
            name="Joseph Shine v. Union of India",
            citation="(2018) 7 SCC 436",
            year=2018,
            key_principle="Section 497 IPC (adultery) unconstitutional; treats women as property of husband",
            must_cite_for=["adultery", "gender equality", "section 497", "women rights", "sexual autonomy"]
        ),
    ],
    "sexual_harassment": [
        LandmarkCase(
            name="Vishaka v. State of Rajasthan",
            citation="(1997) 6 SCC 241",
            year=1997,
            key_principle="Laid down binding guidelines for prevention of sexual harassment at workplace (pre-POSH Act)",
            must_cite_for=["sexual harassment", "workplace", "posh act", "vishaka guidelines", "safe workplace"]
        ),
    ],
    "socio_economic_rights": [
        LandmarkCase(
            name="People's Union for Civil Liberties v. Union of India",
            citation="(2001) 5 SCC 572",
            year=2001,
            key_principle="Right to food integral to right to life under Article 21; state obligated to prevent starvation deaths",
            must_cite_for=["right to food", "welfare", "nfsa", "starvation", "hunger", "social security"]
        ),
    ],
    "affirmative_action": [
        LandmarkCase(
            name="Indra Sawhney v. Union of India",
            citation="(1992) Supp (3) SCC 217",
            year=1992,
            key_principle="50% cap on reservations; 'creamy layer' exclusion for OBCs",
            must_cite_for=["reservation", "sc/st", "obc", "creamy layer", "50 percent cap", "affirmative action"]
        ),
    ],
    "criminal_law": [
        LandmarkCase(
            name="Bachan Singh v. State of Punjab",
            citation="(1980) 2 SCC 684",
            year=1980,
            key_principle="Death penalty only in 'rarest of rare' cases; life imprisonment is rule, death penalty exception",
            must_cite_for=["death penalty", "capital punishment", "rarest of rare", "section 302", "murder"]
        ),
    ],
}


# Statute Map for quick reference
STATUTE_MAP: Dict[str, StatuteProvision] = {
    "bail": StatuteProvision(
        act="Code of Criminal Procedure, 1973",
        sections=["Section 437", "Section 438", "Section 439"],
        key_case="Gurbaksh Singh Sibbia (1980) 2 SCC 565"
    ),
    "defamation": StatuteProvision(
        act="Indian Penal Code, 1860",
        sections=["Section 499", "Section 500"],
        key_case="Subramanian Swamy (2016) 7 SCC 221"
    ),
    "privacy": StatuteProvision(
        act="Constitution of India",
        sections=["Article 21"],
        key_case="Puttaswamy (2017) 10 SCC 1"
    ),
    "free_speech": StatuteProvision(
        act="Constitution of India",
        sections=["Article 19(1)(a)", "Article 19(2)"],
        key_case="Shreya Singhal (2015) 5 SCC 1"
    ),
    "it_act": StatuteProvision(
        act="Information Technology Act, 2000",
        sections=["Section 66A (struck down)", "Section 69", "Section 79"],
        key_case="Shreya Singhal (2015) 5 SCC 1"
    ),
    "dpdpa": StatuteProvision(
        act="Digital Personal Data Protection Act, 2023",
        sections=["Section 6", "Section 8", "Section 10"],
        key_case=None
    ),
    "ipc_general": StatuteProvision(
        act="Indian Penal Code, 1860",
        sections=["Section 295A", "Section 377", "Section 497"],
        key_case="Multiple landmark cases"
    ),
}


# Regex Patterns
SCC_PATTERN = re.compile(r"\(\d{4}\)\s+\d+\s+SCC\s+\d+")
AIR_PATTERN = re.compile(r"AIR\s+\d{4}\s+(SC|Bom|Del|Cal|Guj|Ker|Mad|Pat|Raj)\s+\d+")
INDIAN_CASE_NAME_PATTERN = re.compile(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:\s+v\.\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)")


# Helper Functions

def is_valid_scc_citation(text: str) -> bool:
    """Check if text contains a valid SCC citation."""
    return bool(SCC_PATTERN.search(text))


def extract_citations(text: str) -> List[str]:
    """Extract all SCC and AIR citations from text."""
    scc_matches = SCC_PATTERN.findall(text)
    air_matches = AIR_PATTERN.findall(text)
    return scc_matches + air_matches


def get_all_landmark_cases() -> List[LandmarkCase]:
    """Get all landmark cases as a flat list."""
    all_cases = []
    for cases in LANDMARK_CASES.values():
        all_cases.extend(cases)
    return all_cases


def find_relevant_cases(argument: str) -> List[LandmarkCase]:
    """Find cases that match the given argument."""
    relevant = []
    for case in get_all_landmark_cases():
        if case.matches_argument(argument):
            relevant.append(case)
    return relevant


def get_statute_for_topic(topic: str) -> Optional[StatuteProvision]:
    """Get statute provision for a given topic."""
    topic_lower = topic.lower()
    for key, provision in STATUTE_MAP.items():
        if key in topic_lower or topic_lower in key:
            return provision
    return None


def run_phase1_validation():
    """Run Phase 1 validation tests."""
    all_passed = True
    
    # Test 1: Puttaswamy privacy case
    argument1 = "Aadhaar violates my right to privacy"
    cases1 = find_relevant_cases(argument1)
    puttaswamy_found = any("Puttaswamy" in case.name for case in cases1)
    if puttaswamy_found:
        print("Test 1: ✅ Puttaswamy triggered")
    else:
        print("Test 1: ❌ Puttaswamy NOT triggered")
        all_passed = False
    
    # Test 2: Gurbaksh Singh Sibbia anticipatory bail case
    argument2 = "anticipatory bail under section 438 CrPC"
    cases2 = find_relevant_cases(argument2)
    sibbia_found = any("Sibbia" in case.name for case in cases2)
    if sibbia_found:
        print("Test 2: ✅ Sibbia triggered")
    else:
        print("Test 2: ❌ Sibbia NOT triggered")
        all_passed = False
    
    # Test 3: Ramji Lal Modi Section 295A case
    argument3 = "Section 295A IPC hurting religious sentiments"
    cases3 = find_relevant_cases(argument3)
    modi_found = any("Ramji Lal Modi" in case.name for case in cases3)
    if modi_found:
        print("Test 3: ✅ Ramji Lal Modi triggered")
    else:
        print("Test 3: ❌ Ramji Lal Modi NOT triggered")
        all_passed = False
    
    # Test 4: No false positive - bail should NOT trigger Puttaswamy
    argument4 = "bail application section 437"
    cases4 = find_relevant_cases(argument4)
    puttaswamy_false_positive = any("Puttaswamy" in case.name for case in cases4)
    if not puttaswamy_false_positive:
        print("Test 4: ✅ No Puttaswamy false positive")
    else:
        print("Test 4: ❌ False positive: Puttaswamy triggered for bail")
        all_passed = False
    
    # Test 5: SCC citation validator
    valid = is_valid_scc_citation("(2017) 10 SCC 1")
    invalid = not is_valid_scc_citation("Puttaswamy case")
    if valid and invalid:
        print("Test 5: ✅ SCC citation validator correct")
    else:
        print("Test 5: ❌ SCC validator failed")
        all_passed = False
    
    # Test 6: Bail statute contains Section 438
    bail_statute = get_statute_for_topic("bail")
    has_section_438 = bail_statute is not None and any("Section 438" in section for section in bail_statute.sections)
    if has_section_438:
        print("Test 6: ✅ Bail statute contains Section 438")
    else:
        print("Test 6: ❌ Bail statute missing Section 438")
        all_passed = False
    
    # Final summary
    if all_passed:
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS FAILED")


if __name__ == "__main__":
    run_phase1_validation()
