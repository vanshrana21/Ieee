/**
 * cases-data.js
 * Static database of legal cases for the LegalAI Research platform
 * Contains realistic case data with metadata for filtering and search
 */

const CASES_DATABASE = [
  {
    id: 'case-001',
    title: 'Smith v. Johnson Industries, Inc.',
    court: 'U.S. Supreme Court',
    courtCode: 'scotus',
    jurisdiction: 'federal',
    year: 2024,
    date: 'March 15, 2024',
    docketNo: '23-1456',
    citations: 127,
    citation: '598 U.S. ___ (2024)',
    summary: 'This landmark case addresses the application of employment discrimination laws in the context of AI-driven hiring practices. The Court held that automated systems must comply with Title VII standards and that employers remain liable for discriminatory outcomes even when using third-party AI tools.',
    tags: ['Employment Law', 'AI & Technology', 'Civil Rights'],
    keyPoints: [
      'Employers remain liable for discriminatory outcomes of AI hiring tools under Title VII',
      'Automated systems must meet the same disparate impact standards as traditional hiring practices',
      'Third-party AI vendors do not shield employers from discrimination claims',
      'Employers must audit and validate AI tools for potential bias before deployment',
      'Decision extends to all protected classes under federal employment discrimination law'
    ],
    holdings: 'The Supreme Court held that employers using artificial intelligence systems for hiring decisions remain fully liable under Title VII of the Civil Rights Act when those systems produce discriminatory outcomes. The Court rejected the argument that delegation to third-party AI vendors constitutes a defense against disparate impact claims. Writing for the majority, Justice Roberts emphasized that technological advancement cannot serve as a shield for employment discrimination. The decision requires employers to implement regular auditing procedures and maintain transparency regarding algorithmic decision-making processes.',
    citedBy: [
      { title: 'Anderson v. Tech Corp.', year: 2024 },
      { title: 'Williams v. HR Solutions LLC', year: 2024 },
      { title: 'Brown v. National Retail Chain', year: 2024 }
    ],
    cites: [
      { title: 'Griggs v. Duke Power Co.', citation: '401 U.S. 424 (1971)' },
      { title: 'Watson v. Fort Worth Bank', citation: '487 U.S. 977 (1988)' },
      { title: 'Ricci v. DeStefano', citation: '557 U.S. 557 (2009)' }
    ],
    statutes: [
      { code: '42 U.S.C. § 2000e-2', description: 'Unlawful employment practices (Title VII)' },
      { code: '29 C.F.R. § 1607', description: 'Uniform Guidelines on Employee Selection Procedures' }
    ]
  },
  {
    id: 'case-002',
    title: 'United States v. Digital Privacy Foundation',
    court: '9th Circuit Court of Appeals',
    courtCode: 'ca9',
    jurisdiction: 'federal',
    year: 2023,
    date: 'September 8, 2023',
    docketNo: '22-3847',
    citations: 89,
    citation: '1012 F.3d 456 (9th Cir. 2023)',
    summary: 'The court examined Fourth Amendment protections in the digital age, ruling that warrantless access to encrypted cloud storage violates constitutional privacy rights. The decision significantly impacts law enforcement procedures for obtaining digital evidence.',
    tags: ['Constitutional Law', 'Privacy Rights', 'Digital Evidence'],
    keyPoints: [
      'Fourth Amendment protections extend to encrypted cloud storage',
      'Warrantless access to digital files violates constitutional privacy rights',
      'Cloud service providers cannot consent to searches on behalf of users',
      'Law enforcement must obtain specific warrants for digital evidence',
      'Decision establishes higher standards for digital privacy protection'
    ],
    holdings: 'The Ninth Circuit held that individuals maintain a reasonable expectation of privacy in encrypted cloud storage, and warrantless government access violates the Fourth Amendment. The court distinguished cloud storage from traditional third-party doctrine cases, finding that modern encryption technology creates a protected privacy interest. The decision requires law enforcement to obtain warrants with specific probable cause before accessing encrypted digital files, even when stored with third-party service providers.',
    citedBy: [
      { title: 'State v. CloudTech Services', year: 2024 },
      { title: 'Riley v. Department of Justice', year: 2023 }
    ],
    cites: [
      { title: 'Riley v. California', citation: '573 U.S. 373 (2014)' },
      { title: 'Carpenter v. United States', citation: '585 U.S. ___ (2018)' },
      { title: 'Katz v. United States', citation: '389 U.S. 347 (1967)' }
    ],
    statutes: [
      { code: 'U.S. Const. amend. IV', description: 'Fourth Amendment protection against unreasonable searches' },
      { code: '18 U.S.C. § 2703', description: 'Stored Communications Act provisions' }
    ]
  },
  {
    id: 'case-003',
    title: 'Thompson Medical Corp. v. Federal Trade Commission',
    court: '2nd Circuit Court of Appeals',
    courtCode: 'ca2',
    jurisdiction: 'federal',
    year: 2023,
    date: 'June 22, 2023',
    docketNo: '22-1955',
    citations: 64,
    citation: '987 F.3d 234 (2d Cir. 2023)',
    summary: 'This case clarifies the FTC\'s authority to regulate misleading health claims in pharmaceutical advertising. The court upheld the commission\'s power to seek monetary relief for consumer injury resulting from false marketing practices.',
    tags: ['Administrative Law', 'Consumer Protection', 'Healthcare'],
    keyPoints: [
      'FTC has broad authority to regulate pharmaceutical advertising',
      'Misleading health claims constitute unfair trade practices',
      'Commission can seek monetary relief for consumer injury',
      'Companies liable for substantiation failures in health claims',
      'Decision strengthens consumer protection in healthcare marketing'
    ],
    holdings: 'The Second Circuit affirmed the FTC\'s authority to regulate misleading health claims in pharmaceutical advertising and to seek monetary relief for affected consumers. The court held that companies making health-related claims must possess adequate substantiation before dissemination, and failure to do so constitutes an unfair trade practice under Section 5 of the FTC Act. The decision expands the Commission\'s enforcement tools in healthcare marketing cases.',
    citedBy: [
      { title: 'Natural Health Inc. v. FTC', year: 2024 },
      { title: 'Pharma Solutions v. Commissioner', year: 2023 }
    ],
    cites: [
      { title: 'FTC v. Wyndham Worldwide Corp.', citation: '799 F.3d 236 (3d Cir. 2015)' },
      { title: 'AMG Capital Mgmt. v. FTC', citation: '141 S. Ct. 1341 (2021)' }
    ],
    statutes: [
      { code: '15 U.S.C. § 45', description: 'FTC Act Section 5 - Unfair trade practices' },
      { code: '21 C.F.R. § 202', description: 'FDA prescription drug advertising regulations' }
    ]
  },
  {
    id: 'case-004',
    title: 'Green Energy Alliance v. Environmental Protection Agency',
    court: 'D.C. Circuit Court of Appeals',
    courtCode: 'cadc',
    jurisdiction: 'federal',
    year: 2024,
    date: 'February 14, 2024',
    docketNo: '23-1288',
    citations: 42,
    citation: '1045 F.3d 678 (D.C. Cir. 2024)',
    summary: 'The court addressed the EPA\'s regulatory authority under the Clean Air Act regarding carbon emissions from new power plants. The decision impacts federal environmental policy and state implementation plans for greenhouse gas reduction.',
    tags: ['Environmental Law', 'Administrative Law', 'Energy Policy'],
    keyPoints: [
      'EPA has authority to regulate carbon emissions from power plants',
      'Clean Air Act encompasses greenhouse gas regulation',
      'State implementation plans must address climate impacts',
      'Agency must consider economic feasibility in rulemaking',
      'Decision affects national energy policy and climate initiatives'
    ],
    holdings: 'The D.C. Circuit upheld the EPA\'s authority to regulate carbon emissions from new power plants under the Clean Air Act. The court found that greenhouse gases fall within the statute\'s definition of air pollutants and that the agency\'s regulatory approach reasonably balances environmental protection with economic considerations. The decision requires states to incorporate carbon reduction strategies into their implementation plans.',
    citedBy: [
      { title: 'Utility Coalition v. EPA', year: 2024 }
    ],
    cites: [
      { title: 'Massachusetts v. EPA', citation: '549 U.S. 497 (2007)' },
      { title: 'West Virginia v. EPA', citation: '142 S. Ct. 2587 (2022)' }
    ],
    statutes: [
      { code: '42 U.S.C. § 7411', description: 'Clean Air Act standards for new sources' },
      { code: '40 C.F.R. § 60', description: 'EPA emission standards regulations' }
    ]
  },
  {
    id: 'case-005',
    title: 'Martinez v. City of Los Angeles',
    court: 'California Supreme Court',
    courtCode: 'ca-supreme',
    jurisdiction: 'state',
    year: 2023,
    date: 'November 3, 2023',
    docketNo: 'S267890',
    citations: 156,
    citation: '15 Cal.5th 123 (2023)',
    summary: 'A significant decision on municipal liability for homelessness policies, establishing that cities may face civil rights claims for enforcement actions that criminalize homelessness without providing adequate alternative shelter options.',
    tags: ['Civil Rights', 'Municipal Law', 'Housing Policy'],
    keyPoints: [
      'Cities cannot criminalize homelessness without providing alternatives',
      'Enforcement actions must respect constitutional protections',
      'Municipal liability extends to inadequate shelter policies',
      'Eighth Amendment bars cruel and unusual punishment for status',
      'Decision requires comprehensive approach to homelessness'
    ],
    holdings: 'The California Supreme Court held that municipalities may face civil rights liability when enforcing ordinances that effectively criminalize homelessness without providing adequate shelter alternatives. The court found that such enforcement violates the Eighth Amendment\'s prohibition on cruel and unusual punishment when individuals have no reasonable alternative to public spaces. The decision requires cities to demonstrate sufficient shelter capacity before enforcement actions.',
    citedBy: [
      { title: 'Johnson v. City of San Francisco', year: 2024 },
      { title: 'Homeless Coalition v. County of Orange', year: 2024 },
      { title: 'Smith v. City of Sacramento', year: 2024 }
    ],
    cites: [
      { title: 'Martin v. City of Boise', citation: '920 F.3d 584 (9th Cir. 2019)' },
      { title: 'Robinson v. California', citation: '370 U.S. 660 (1962)' }
    ],
    statutes: [
      { code: 'Cal. Gov. Code § 65583', description: 'Housing element requirements' },
      { code: 'U.S. Const. amend. VIII', description: 'Eighth Amendment protections' }
    ]
  },
  {
    id: 'case-006',
    title: 'DataTech Solutions Inc. v. Commissioner of Internal Revenue',
    court: 'U.S. Tax Court',
    courtCode: 'tax-court',
    jurisdiction: 'federal',
    year: 2024,
    date: 'January 18, 2024',
    docketNo: '24567-22',
    citations: 38,
    citation: '162 T.C. No. 4 (2024)',
    summary: 'The Tax Court ruled on the deductibility of cryptocurrency mining expenses and the classification of digital assets for tax purposes. The decision provides guidance on reporting requirements for blockchain-based business operations.',
    tags: ['Tax Law', 'Cryptocurrency', 'Business Law'],
    keyPoints: [
      'Cryptocurrency mining expenses are deductible business costs',
      'Digital assets classified as property for tax purposes',
      'Specific identification method applies to crypto transactions',
      'Mining rewards constitute ordinary income when received',
      'Decision clarifies reporting requirements for blockchain businesses'
    ],
    holdings: 'The Tax Court held that cryptocurrency mining operations constitute trade or business activities, making related expenses deductible under Section 162. The court classified digital assets as property under existing tax code provisions and permitted the use of specific identification for determining basis in cryptocurrency transactions. Mining rewards are taxable as ordinary income upon receipt, with fair market value at the time of receipt establishing basis.',
    citedBy: [
      { title: 'CryptoMining LLC v. Commissioner', year: 2024 }
    ],
    cites: [
      { title: 'Commissioner v. Groetzinger', citation: '480 U.S. 23 (1987)' },
      { title: 'Cottage Savings Ass\'n v. Commissioner', citation: '499 U.S. 554 (1991)' }
    ],
    statutes: [
      { code: '26 U.S.C. § 162', description: 'Trade or business expenses deduction' },
      { code: '26 U.S.C. § 1012', description: 'Basis of property' }
    ]
  },
  {
    id: 'case-007',
    title: 'Robinson v. State Medical Board',
    court: 'State Supreme Court',
    courtCode: 'state-supreme',
    jurisdiction: 'state',
    year: 2023,
    date: 'August 29, 2023',
    docketNo: 'SC-2023-0456',
    citations: 73,
    citation: '456 State Rep. 789 (2023)',
    summary: 'This case examines professional licensing standards for telemedicine practitioners and cross-border healthcare delivery. The court established criteria for remote medical practice and state board jurisdiction over out-of-state providers.',
    tags: ['Healthcare Law', 'Professional Licensing', 'Telemedicine'],
    keyPoints: [
      'Telemedicine providers must meet state licensing requirements',
      'Physical presence not required for jurisdiction over practitioners',
      'State boards can regulate out-of-state providers treating local patients',
      'Minimum contact standards apply to medical licensing enforcement',
      'Decision establishes framework for interstate telemedicine practice'
    ],
    holdings: 'The State Supreme Court held that medical boards maintain jurisdiction over out-of-state practitioners providing telemedicine services to in-state patients. The court established that treating patients within the state constitutes sufficient minimum contacts for regulatory jurisdiction, regardless of the provider\'s physical location. The decision requires telemedicine practitioners to obtain appropriate licensure in each state where they treat patients.',
    citedBy: [
      { title: 'TeleMed Services v. Licensing Board', year: 2024 },
      { title: 'Doctor\'s Alliance v. State', year: 2024 }
    ],
    cites: [
      { title: 'International Shoe Co. v. Washington', citation: '326 U.S. 310 (1945)' }
    ],
    statutes: [
      { code: 'State Med. Code § 2052', description: 'Medical practice licensing requirements' },
      { code: 'State Tele. Act § 1234', description: 'Telemedicine practice regulations' }
    ]
  },
  {
    id: 'case-008',
    title: 'Peterson v. National Labor Relations Board',
    court: '7th Circuit Court of Appeals',
    courtCode: 'ca7',
    jurisdiction: 'federal',
    year: 2024,
    date: 'April 11, 2024',
    docketNo: '23-2134',
    citations: 51,
    citation: '1056 F.3d 901 (7th Cir. 2024)',
    summary: 'The decision addresses worker classification in the gig economy, determining that certain independent contractors qualify for collective bargaining rights under the National Labor Relations Act based on the economic realities test.',
    tags: ['Labor Law', 'Gig Economy', 'Workers\' Rights'],
    keyPoints: [
      'Economic realities test applies to gig worker classification',
      'Some independent contractors qualify for NLRA protections',
      'Platform control over work conditions indicates employee status',
      'Collective bargaining rights extend to certain gig workers',
      'Decision impacts classification standards across industries'
    ],
    holdings: 'The Seventh Circuit held that gig economy workers may qualify as employees under the NLRA when applying the economic realities test, despite contractual classification as independent contractors. The court examined factors including platform control over work conditions, pricing, and worker dependence on the platform. The decision entitles qualifying workers to collective bargaining protections and union organizing rights.',
    citedBy: [
      { title: 'Rideshare Drivers v. Platform Inc.', year: 2024 },
      { title: 'Delivery Workers Union v. NLRB', year: 2024 }
    ],
    cites: [
      { title: 'NLRB v. United Insurance Co.', citation: '390 U.S. 254 (1968)' },
      { title: 'FedEx Home Delivery v. NLRB', citation: '563 F.3d 492 (D.C. Cir. 2009)' }
    ],
    statutes: [
      { code: '29 U.S.C. § 152(3)', description: 'NLRA definition of employee' },
      { code: '29 U.S.C. § 157', description: 'Employee rights under NLRA' }
    ]
  },
  {
    id: 'case-009',
    title: 'Anderson v. Social Media Platform Corp.',
    court: 'U.S. Supreme Court',
    courtCode: 'scotus',
    jurisdiction: 'supreme',
    year: 2024,
    date: 'May 20, 2024',
    docketNo: '23-2789',
    citations: 203,
    citation: '599 U.S. ___ (2024)',
    summary: 'Landmark decision on Section 230 immunity for social media platforms, clarifying the scope of protection for content moderation decisions and establishing standards for when platforms may lose immunity for algorithmic recommendations.',
    tags: ['Internet Law', 'Free Speech', 'Technology'],
    keyPoints: [
      'Section 230 immunity has limits for algorithmic content promotion',
      'Platforms remain protected for traditional content moderation',
      'Active promotion through algorithms may exceed immunity scope',
      'Publishers versus distributors distinction applies to recommendations',
      'Decision affects platform liability for user-generated content'
    ],
    holdings: 'The Supreme Court clarified that Section 230 immunity protects platforms\' traditional content moderation decisions but may not extend to active algorithmic promotion of harmful content. The Court distinguished between passive hosting and active editorial decisions, holding that recommendation algorithms that materially contribute to illegal conduct fall outside Section 230\'s protection. The decision preserves immunity for good-faith content moderation while creating liability exposure for algorithm-driven promotion.',
    citedBy: [
      { title: 'VideoShare Inc. v. Content Creators', year: 2024 },
      { title: 'State v. Tech Platform LLC', year: 2024 }
    ],
    cites: [
      { title: 'Reno v. ACLU', citation: '521 U.S. 844 (1997)' },
      { title: 'Zeran v. America Online', citation: '129 F.3d 327 (4th Cir. 1997)' }
    ],
    statutes: [
      { code: '47 U.S.C. § 230', description: 'Protection for private blocking and screening' },
      { code: '47 U.S.C. § 230(c)(1)', description: 'Publisher liability immunity' }
    ]
  },
  {
    id: 'case-010',
    title: 'Chen v. Department of Education',
    court: 'D.C. Circuit Court of Appeals',
    courtCode: 'cadc',
    jurisdiction: 'federal',
    year: 2023,
    date: 'December 15, 2023',
    docketNo: '23-5012',
    citations: 91,
    citation: '1034 F.3d 445 (D.C. Cir. 2023)',
    summary: 'The court examined the Department of Education\'s authority to implement student loan forgiveness programs, analyzing the scope of executive power under the Higher Education Act and addressing constitutional separation of powers concerns.',
    tags: ['Education Law', 'Administrative Law', 'Constitutional Law'],
    keyPoints: [
      'Executive authority for loan forgiveness requires clear statutory authorization',
      'Major questions doctrine limits agency discretion on significant economic policies',
      'Congressional intent determines scope of delegated authority',
      'Separation of powers constrains executive action on fiscal matters',
      'Decision impacts future student debt relief initiatives'
    ],
    holdings: 'The D.C. Circuit held that broad-based student loan forgiveness requires explicit Congressional authorization and cannot be implemented through administrative interpretation of general statutory provisions. Applying the major questions doctrine, the court found that the economic and political significance of mass debt cancellation exceeds the scope of authority delegated to the Department of Education. The decision reinforces separation of powers principles in administrative law.',
    citedBy: [
      { title: 'Student Coalition v. Secretary of Education', year: 2024 }
    ],
    cites: [
      { title: 'West Virginia v. EPA', citation: '142 S. Ct. 2587 (2022)' },
      { title: 'Utility Air Regulatory Group v. EPA', citation: '573 U.S. 302 (2014)' }
    ],
    statutes: [
      { code: '20 U.S.C. § 1082', description: 'Higher Education Act administrative provisions' },
      { code: '20 U.S.C. § 1098bb', description: 'Student loan modification authority' }
    ]
  }
];

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
  module.exports = CASES_DATABASE;
}
// Make available globally (required for browser usage)
window.CASES_DATABASE = CASES_DATABASE;
