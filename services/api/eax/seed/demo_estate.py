"""Laptop demo model "Protea Insurance (demo estate)" (build phase 8.2, D161).

A fictitious South African insurer with a whole estate on ArchiMate 4, so every viewpoint (VP-01 to
VP-25, and the business architecture viewpoints with the EA Explorer extensions, D345), standard report, TOGAF catalogue and matrix and dependency report has something to show:
motivation, strategy, business, application, technology and implementation and migration, with
values for the attributes the reports use (lifecycle, criticality, cost in USD, TIME, fit scores,
end of life, data classification, maturity...). Every company, product and vendor name is invented.

Loaded with the laptop test models (eax.seed.build.test_models_sql). Relationships keep to the
ArchiMate 4 allowed relationships of the template (eax.seed.archimate4).
"""

from __future__ import annotations

DEMO_KEY = "protea-demo-estate"
DEMO_NAME = "Protea Insurance (demo estate)"

# ---------------------------------------------------------------- entities
# (type, name, description, parent name or "", {attribute: value})
E: list[tuple[str, str, str, str, dict]] = []


def ent(t: str, name: str, desc: str = "", parent: str = "", **attrs) -> None:
    E.append((t, name, desc, parent, attrs))


# motivation
for name, desc in [("Chief Executive", "Accountable for strategy and results"),
                   ("Chief Information Officer", "Accountable for information technology"),
                   ("Chief Financial Officer", "Accountable for finance and cost"),
                   ("Chief Risk Officer", "Accountable for risk and compliance"),
                   ("Prudential Regulator", "Supervises the insurer's soundness"),
                   ("Policyholders", "Customers who hold policies"),
                   ("Brokers", "Independent intermediaries who sell the products")]:
    ent("Stakeholder", name, desc, Owner="Strategy Office")
for name, desc in [("Digital customer expectations", "Customers expect to buy and claim online at any hour"),
                   ("Regulatory change", "New conduct and solvency rules and data protection law"),
                   ("Cost pressure", "Expense ratio above peers"),
                   ("Ageing core systems", "Core platforms out of support within three years"),
                   ("Cyber threats", "Rising attacks on financial services")]:
    ent("Driver", name, desc, Owner="Strategy Office")
for name, desc in [("Claims take 21 days to settle", "Settlement time well behind the market"),
                   ("Expense ratio 34%", "Six points above the peer average"),
                   ("Three platforms past end of support", "Policy, billing and data warehouse platforms"),
                   ("Customer data held in nine places", "No single view of the customer")]:
    ent("Assessment", name, desc, Owner="Strategy Office")
for name, desc, pr, measure in [
        ("Grow digital sales", "Sell more policies online", "Must", "40% of new policies sold online by 2028"),
        ("Settle claims faster", "Reduce settlement time", "Must", "Average settlement under 7 days"),
        ("Lower the cost to serve", "Reduce operating expense", "Must", "Expense ratio 28% by 2028"),
        ("Stay compliant", "Meet every regulatory obligation", "Must", "No material findings"),
        ("Modernise the core", "Replace end-of-life platforms", "Should", "No platform past end of support")]:
    ent("Goal", name, desc, Owner="Chief Executive", Priority=pr, Measure=measure)
for name, measure in [("Online first notice of loss", "70% of claims lodged online"),
                      ("Straight-through underwriting", "60% of simple policies issued without a person"),
                      ("One customer record", "Every customer held once"),
                      ("Cloud-hosted core", "Core platforms in the cloud")]:
    ent("Outcome", name, f"Outcome: {name.lower()}", Owner="Strategy Office", Measure=measure)
for name, desc in [("Cloud first", "New solutions are cloud hosted unless there is a reason not to"),
                   ("Buy before build", "Prefer configurable products to bespoke code"),
                   ("Data is an asset", "Data is owned, classified and of known quality"),
                   ("Secure by design", "Security is designed in, not added later"),
                   ("Reuse before buy", "Use what the group already has first"),
                   ("API first", "Systems share data through managed APIs")]:
    ent("Principle", name, desc, Owner="Architecture Board", Priority="Must")
for name, pr in [("Customers can lodge claims online", "Must"), ("Policies can be bought online", "Must"),
                 ("Personal information is protected", "Must"), ("Claims are paid within 48 hours of approval", "Should"),
                 ("Brokers can quote through an API", "Should"), ("Single sign-on for staff", "Should"),
                 ("Regulatory returns produced automatically", "Must"), ("Core systems hosted in the cloud", "Could")]:
    ent("Requirement", name, f"Requirement: {name.lower()}", Owner="Architecture Board", Priority=pr)
ent("Meaning", "Peace of mind", "What cover means to a policyholder")
ent("Value", "Faster payouts", "Value of quicker claim settlement to policyholders")
ent("Value", "Lower premiums", "Value of a lower cost base passed to customers")

# strategy
CAPS = {
    "Customer Management": ["Customer Onboarding", "Customer Service", "Customer Insight"],
    "Product Management": ["Product Design", "Pricing", "Product Launch"],
    "Sales and Distribution": ["Direct Sales", "Broker Management", "Quoting"],
    "Underwriting": ["Risk Assessment", "Policy Issue", "Reinsurance"],
    "Policy Administration": ["Policy Servicing", "Renewals", "Billing and Collections"],
    "Claims Management": ["Claims Lodgement", "Claims Assessment", "Claims Settlement", "Fraud Detection"],
    "Finance": ["Financial Accounting", "Actuarial Valuation", "Regulatory Reporting"],
    "Risk and Compliance": ["Risk Management", "Compliance Monitoring", "Data Protection"],
    "Technology Management": ["Infrastructure Management", "Security Management", "Data Management"],
}
MATURITY = ["1 - Initial", "2 - Managed", "3 - Defined", "4 - Measured", "5 - Optimised"]
IMPORTANCE, INVESTMENT = ["High", "Medium", "Low"], ["Invest", "Sustain", "Reduce"]   # D345: the capability map's heat
for i, (l1, l2s) in enumerate(CAPS.items()):
    ent("Capability", l1, f"Ability to manage {l1.lower()}", Owner="COO", CapabilityLevel=1,
        Maturity=MATURITY[(i + 1) % 4 + 1], Criticality=5 if i < 6 else 4, Lifecycle="Production",
        Importance=IMPORTANCE[0 if i < 5 else 1], Investment=INVESTMENT[i % 3])
    for j, l2 in enumerate(l2s):
        ent("Capability", l2, f"Ability for {l2.lower()}", parent=l1, Owner="COO", CapabilityLevel=2,
            Maturity=MATURITY[(i + j) % 5], Criticality=(i + j) % 5 + 1, Lifecycle="Production",
            Importance=IMPORTANCE[(i + j) % 3], Investment=INVESTMENT[(i * 2 + j) % 3])
for name, desc in [("Skilled claims assessors", "People who assess claims"),
                   ("Actuarial team", "Pricing and valuation skills"),
                   ("Customer data", "What the insurer knows about its customers"),
                   ("Broker network", "Relationships with 1,200 brokers")]:
    ent("Resource", name, desc, Owner="COO")
for name, desc in [("Digitise claims", "Move claims online end to end"),
                   ("Move the core to the cloud", "Replace on-premises core platforms with cloud services"),
                   ("Build a single customer view", "One customer record across products"),
                   ("Open up to brokers through APIs", "Let brokers quote and bind through APIs")]:
    ent("CourseOfAction", name, desc, Owner="Strategy Office")
VSTREAMS = {"Acquire a Customer": ["Attract", "Quote", "Buy", "Onboard"],
            "Settle a Claim": ["Lodge", "Assess", "Approve", "Pay"],
            "Renew a Policy": ["Remind", "Review", "Renew"]}
# the stages are Value Stream Stages (D345: an EA Explorer extension), in order, with entry and exit criteria
STAGE_DETAIL = {"Attract": ("A prospect shows interest", "The prospect asks for a quote", "Awareness of the right cover"),
                "Quote": ("A quote is asked for", "A priced quote is accepted", "A fair price, at once"),
                "Buy": ("The quote is accepted", "The policy is paid for and issued", "Cover in place"),
                "Onboard": ("The policy is issued", "The customer uses self-service", "Knowing how to use the cover"),
                "Lodge": ("Something insured is lost or damaged", "The claim is registered", "Being heard straight away"),
                "Assess": ("The claim is registered", "The claim is valued", "A clear, fair assessment"),
                "Approve": ("The claim is valued", "Payment is authorised", "A decision without delay"),
                "Pay": ("Payment is authorised", "The money is in the claimant's account", "Being made whole"),
                "Remind": ("Sixty days before renewal", "The customer is told the new terms", "No surprises"),
                "Review": ("The customer has the new terms", "The terms are agreed or changed", "Cover that still fits"),
                "Renew": ("The terms are agreed", "The renewed policy is in force", "Continued cover")}
for vs, stages in VSTREAMS.items():
    ent("ValueStream", vs, f"End to end: {vs.lower()}", Owner="COO", Lifecycle="Production")
    for n, s in enumerate(stages, start=1):
        entry, exit_, value = STAGE_DETAIL[s]
        ent("ValueStreamStage", f"{vs}: {s}", f"Stage {s.lower()} of {vs.lower()}", parent=vs, Owner="COO",
            StageOrder=n, EntryCriteria=entry, ExitCriteria=exit_, ValueItem=value)

# business
for name, _loc in [("Executive Committee", "Cape Town Head Office"), ("Claims Department", "Johannesburg Operations Centre"),
                  ("Underwriting Department", "Cape Town Head Office"), ("Sales Department", "Johannesburg Operations Centre"),
                  ("Finance Department", "Cape Town Head Office"), ("IT Department", "Johannesburg Operations Centre"),
                  ("Risk and Compliance Office", "Cape Town Head Office"), ("Customer Contact Centre", "Durban Contact Centre")]:
    ent("BusinessActor", name, f"The {name.lower()}", Owner="COO")
for name in ["Claims Assessor", "Underwriter", "Sales Agent", "Contact Centre Agent", "Actuary", "Compliance Officer",
             "Broker", "Policyholder", "Data Steward", "Finance Clerk"]:
    ent("Role", name, f"The role of {name.lower()}", Owner="COO", Domain="Business")
ent("Collaboration", "Claims Fraud Panel", "Claims, risk and legal deciding on suspected fraud", Owner="COO", Domain="Business")
ent("BusinessInterface", "Branch Counter", "Walk-in service at branches", Owner="COO")
ent("BusinessInterface", "Contact Centre Line", "Telephone service", Owner="COO")
ent("BusinessInterface", "Broker Desk", "Service desk for brokers", Owner="COO")
for name, lvl in [("Lodge Claim", 2), ("Assess Claim", 2), ("Approve Claim", 2), ("Pay Claim", 2), ("Detect Fraud", 3),
                  ("Quote Policy", 2), ("Underwrite Policy", 2), ("Issue Policy", 2), ("Collect Premium", 2),
                  ("Renew Policy", 2), ("Change Policy", 2), ("Onboard Customer", 2), ("Produce Regulatory Return", 2),
                  ("Value Liabilities", 2), ("Close Financial Period", 2)]:
    ent("Process", name, f"Process: {name.lower()}", Owner="COO", ProcessLevel=lvl, Domain="Business", Lifecycle="Production")
for name in ["Claims Handling", "Underwriting Operations", "Billing", "Customer Servicing", "Actuarial Work", "Financial Control"]:
    ent("Function", name, f"Business function: {name.lower()}", Owner="COO", Domain="Business", Lifecycle="Production")
for name, crit in [("Claims Service", 5), ("Policy Purchase Service", 5), ("Policy Servicing Service", 4),
                   ("Premium Collection Service", 4), ("Customer Support Service", 3), ("Broker Quoting Service", 4),
                   ("Regulatory Reporting Service", 5), ("Fraud Screening Service", 4)]:
    ent("Service", name, f"Business service: {name.lower()}", Owner="COO", Domain="Business", Criticality=crit,
        Lifecycle="Production")
for name in ["First Notice of Loss", "Policy Renewal Due", "Month End", "Premium Missed"]:
    ent("Event", name, f"Business event: {name.lower()}", Owner="COO", Domain="Business")
for name, cls in [("Customer", "Confidential"), ("Policy", "Confidential"), ("Claim", "Confidential"),
                  ("Premium", "Internal"), ("Quote", "Internal"), ("Broker Agreement", "Confidential"),
                  ("Regulatory Return", "Restricted"), ("Medical Report", "Restricted")]:
    ent("BusinessObject", name, f"Business object: {name.lower()}", Owner="Data Office", DataClassification=cls)
for name in ["Motor Cover", "Home Cover", "Funeral Plan", "Life Cover", "Business Cover"]:
    ent("Product", name, f"Insurance product: {name.lower()}", Owner="Product Management", Lifecycle="Production")
# D345 (EA Explorer extensions): a product's lifecycle stages, business scenarios, controls, contracts and measures
LIFECYCLE = [("Design", "A need is found and approved", "The product is priced and approved"),
             ("Launch", "The product is approved", "The first thousand policies are sold"),
             ("Grow", "A thousand policies sold", "Sales growth below 5% a year"),
             ("Mature", "Growth below 5% a year", "A decision to replace or withdraw"),
             ("Withdraw", "The decision to withdraw", "The last policy runs off")]
for prod in ("Motor Cover", "Funeral Plan"):
    for n, (st, entry, exit_) in enumerate(LIFECYCLE, start=1):
        ent("ProductLifecycleStage", f"{prod}: {st}", f"{st} stage of {prod.lower()}", parent=prod, Owner="Product Management",
            StageOrder=n, EntryCriteria=entry, ExitCriteria=exit_)
ent("BusinessScenario", "Claim lodged online after a hailstorm", "A storm brings ten times the usual claims in a day",
    Owner="Claims Operations", Problem="After a hailstorm thousands of motor and home claims arrive at once; the contact centre "
    "cannot take them and claimants wait days to be heard.", Environment="Claims are lodged by telephone and keyed into the "
    "claims platform; assessors are booked by hand.", DesiredOutcome="Claimants lodge online with photos in minutes and simple "
    "claims are settled the same day.")
ent("BusinessScenario", "Broker binds cover through an API", "A broker's own system quotes and binds Protea cover",
    Owner="Broker Services", Problem="Brokers rekey quotes into the broker portal, so they place business with insurers that "
    "connect to their systems.", Environment="Brokers use their own platforms; Protea offers only a web portal.",
    DesiredOutcome="Brokers quote and bind from their own systems through Protea's API.")
for name, desc, pr in [("Four-eyes approval of large claims", "Claims over R250 000 need a second approver", "Must"),
                       ("Sanctions screening at onboarding", "Every new customer is screened against sanctions lists", "Must"),
                       ("Premium reconciliation each month", "Collected premiums agree with the policy book", "Should")]:
    ent("Control", name, desc, Owner="Risk and Compliance Office", Priority=pr)
for name, vendor, start, end, cost in [("Cloud hosting agreement", "Atlas Cloud Services", "2024-04-01", "2027-03-31", 6400000),
                                       ("Policy administration licence", "Kestrel Software", "2021-07-01", "2026-06-30", 4100000),
                                       ("Repairer panel agreement", "Panel of repairers", "2025-01-01", "2027-12-31", 0)]:
    ent("Contract", name, f"Contract: {name.lower()}", Owner="Procurement", Vendor=vendor, StartDate=start, EndDate=end,
        AnnualCost=cost)
for name, how, target in [("Days to settle a claim", "Median days from lodgement to payment", "7 days by 2028"),
                          ("Share of claims lodged online", "Online claims as a share of all claims", "70% by 2028"),
                          ("Expense ratio", "Operating expense as a share of premium", "28% by 2028")]:
    ent("Measure", name, f"Measure: {name.lower()}", Owner="Strategy Office", Measure=how, Target=target)

# application
APPS = [
    # name, owner, lifecycle, crit, vendor, version, hosting, golive, retire, cost, state, time, ff, tf
    ("Policy Administration System", "Head of Policy IT", "Phase Out", 5, "Aloe Systems", "10.2", "On-premises", "2009-03-01",
     "2028-06-30", 2400000, "Baseline", "Migrate", 3, 2),
    ("Cloud Policy Platform", "Head of Policy IT", "Phase In", 5, "Baobab Software", "3.1", "SaaS", "2027-02-01", "",
     1800000, "Target", "Invest", 4, 5),
    ("Claims Platform", "Head of Claims IT", "Production", 5, "Cederberg Claims", "9.0", "SaaS", "2021-07-15", "",
     1500000, "Baseline", "Invest", 4, 4),
    ("Fraud Analytics", "Head of Claims IT", "Production", 4, "Dune Analytics", "5.4", "SaaS", "2022-05-01", "",
     380000, "Baseline", "Invest", 4, 4),
    ("Billing Engine", "Head of Finance IT", "Production", 5, "Aloe Systems", "7.8", "On-premises", "2011-01-10",
     "2027-12-31", 900000, "Baseline", "Migrate", 3, 2),
    ("Payments Hub", "Head of Finance IT", "Production", 5, "Ebony Payments", "4.0", "PaaS", "2020-09-01", "",
     420000, "Baseline", "Invest", 4, 4),
    ("General Ledger", "Head of Finance IT", "Production", 4, "Fynn Finance", "12.1", "SaaS", "2019-04-01", "",
     610000, "Baseline", "Tolerate", 4, 3),
    ("Actuarial Modelling", "Chief Actuary", "Production", 4, "Gecko Actuarial", "8.2", "IaaS", "2016-06-01", "",
     550000, "Baseline", "Tolerate", 4, 3),
    ("Regulatory Reporting Tool", "Head of Finance IT", "Production", 5, "Hadeda Reporting", "2.6", "On-premises", "2015-11-01",
     "2027-06-30", 300000, "Baseline", "Migrate", 2, 2),
    ("Customer Portal", "Head of Digital", "Production", 4, "In-house", "2.3", "PaaS", "2022-03-01", "", 450000,
     "Baseline", "Invest", 4, 5),
    ("Mobile App", "Head of Digital", "Production", 4, "In-house", "1.9", "PaaS", "2023-08-01", "", 320000,
     "Baseline", "Invest", 4, 4),
    ("Broker Portal", "Head of Digital", "Production", 4, "Impala Web", "6.0", "IaaS", "2014-02-01", "2027-09-30",
     260000, "Baseline", "Eliminate", 2, 2),
    ("Broker API Gateway", "Head of Integration", "Phase In", 4, "Jacana Integration", "1.2", "PaaS", "2026-10-01", "",
     180000, "Target", "Invest", 4, 5),
    ("Integration Platform", "Head of Integration", "Production", 5, "Jacana Integration", "11.0", "PaaS", "2018-05-01", "",
     520000, "Baseline", "Invest", 4, 4),
    ("Customer Master Data Hub", "Head of Data", "Phase In", 4, "Kudu Data", "2.0", "SaaS", "2026-11-01", "", 400000,
     "Target", "Invest", 4, 5),
    ("CRM", "Head of Digital", "Production", 4, "Lourie CRM", "21.4", "SaaS", "2019-10-01", "", 700000, "Baseline",
     "Tolerate", 3, 4),
    ("Contact Centre Telephony", "Head of Infrastructure", "Production", 3, "Mamba Voice", "15.2", "SaaS", "2020-01-01", "",
     240000, "Baseline", "Tolerate", 3, 3),
    ("Document Management", "Head of Infrastructure", "Production", 3, "Nyala Content", "7.0", "On-premises", "2013-07-01",
     "2028-03-31", 210000, "Baseline", "Migrate", 3, 2),
    ("Data Warehouse", "Head of Data", "Phase Out", 4, "Oribi Data", "9.6", "On-premises", "2010-05-01", "2027-03-31",
     650000, "Baseline", "Eliminate", 2, 1),
    ("Cloud Data Platform", "Head of Data", "Phase In", 4, "Kudu Data", "1.5", "PaaS", "2026-06-01", "", 520000, "Target",
     "Invest", 4, 5),
    ("Underwriting Rules Engine", "Head of Policy IT", "Production", 4, "Pangolin Rules", "6.3", "IaaS", "2017-09-01", "",
     290000, "Baseline", "Tolerate", 3, 3),
    ("Quote Engine", "Head of Policy IT", "Production", 4, "In-house", "3.4", "IaaS", "2016-03-01", "2027-12-31", 190000,
     "Baseline", "Migrate", 3, 2),
    ("Identity and Access Management", "Head of Security", "Production", 5, "Quagga Identity", "8.1", "SaaS", "2021-02-01",
     "", 260000, "Baseline", "Invest", 4, 4),
    ("Security Monitoring", "Head of Security", "Production", 5, "Rooikat Security", "4.2", "SaaS", "2022-11-01", "",
     340000, "Baseline", "Invest", 4, 4),
    ("HR System", "Head of HR", "Production", 2, "Sable People", "5.0", "SaaS", "2018-01-01", "", 150000, "Baseline",
     "Tolerate", 3, 4),
    ("Email Campaigns", "Head of Marketing", "Production", 2, "Tern Marketing", "3.3", "SaaS", "2021-04-01", "", 90000,
     "Baseline", "Tolerate", 3, 4),
    ("Reinsurance Administration", "Head of Finance IT", "Production", 3, "Umfolozi Re", "4.4", "On-premises", "2012-08-01",
     "2028-12-31", 230000, "Baseline", "Migrate", 3, 2),
    ("Complaints Tracker", "Head of Risk IT", "Production", 2, "In-house", "1.1", "On-premises", "2015-05-01", "", 40000,
     "Baseline", "Eliminate", 2, 2),
]
for (name, owner, life, crit, vendor, version, hosting, golive, retire, cost, state, time_, ff, tf) in APPS:
    attrs = dict(Owner=owner, Lifecycle=life, Criticality=crit, Vendor=vendor, Version=version, Hosting=hosting,
                 GoLiveDate=golive, AnnualCost=cost, ArchitectureState=state, TimeClassification=time_,
                 FunctionalFit=ff, TechnicalFit=tf, LandscapeLevel="Segment")
    if retire:
        attrs["RetirementDate"] = retire
    ent("ApplicationComponent", name, f"Application: {name}", **attrs)
for name in ["Policy API", "Claims API", "Payments API", "Customer API", "Broker Quote API", "Ledger File Interface"]:
    ent("ApplicationInterface", name, f"Application interface: {name}", Owner="Head of Integration", Lifecycle="Production")
for name, crit in [("Policy Data Service", 5), ("Claims Data Service", 5), ("Payment Service", 5), ("Customer Data Service", 4),
                   ("Quote Calculation Service", 4), ("Fraud Scoring Service", 4), ("Identity Service", 5),
                   ("Reporting Data Service", 3)]:
    ent("Service", name, f"Application service: {name.lower()}", Owner="Head of Integration", Domain="Application",
        Criticality=crit, Lifecycle="Production")
for name in ["Validate Claim", "Calculate Premium", "Score Fraud Risk", "Generate Policy Documents"]:
    ent("Function", name, f"Application function: {name.lower()}", Owner="Head of Integration", Domain="Application",
        Lifecycle="Production")
for name, cls in [("Policy Record", "Confidential"), ("Claim Record", "Confidential"), ("Customer Record", "Confidential"),
                  ("Payment Instruction", "Restricted"), ("Premium Record", "Internal"), ("Quote Record", "Internal"),
                  ("General Ledger Entry", "Internal"), ("Regulatory Return File", "Restricted"),
                  ("Fraud Score", "Confidential"), ("Policy Document", "Confidential"), ("Broker Record", "Internal"),
                  ("Actuarial Data Set", "Confidential")]:
    ent("DataObject", name, f"Data object: {name.lower()}", Owner="Data Office", DataClassification=cls)

# technology
TECH = [
    # type, name, vendor, version, hosting, lifecycle, crit, retire, cost
    ("Node", "Primary Data Centre Cluster", "Vervet Hardware", "6.5", "On-premises", "Phase Out", 5, "2028-06-30", 900000),
    ("Node", "Disaster Recovery Cluster", "Vervet Hardware", "6.5", "On-premises", "Phase Out", 5, "2028-06-30", 600000),
    ("Node", "Cloud Landing Zone", "Weaver Cloud", "2.0", "IaaS", "Production", 5, "", 1100000),
    ("Node", "Container Platform", "Weaver Cloud", "1.29", "PaaS", "Production", 5, "", 380000),
    ("Node", "Mainframe Partition", "Xerus Systems", "2.4", "On-premises", "Retiring", 4, "2027-03-31", 750000),
    ("SystemSoftware", "Relational Database 12", "Yellowwood Data", "12.2", "On-premises", "Retiring", 5, "2026-12-31", 480000),
    ("SystemSoftware", "Relational Database 19", "Yellowwood Data", "19.3", "On-premises", "Production", 5, "2027-04-30", 520000),
    ("SystemSoftware", "Managed Cloud Database", "Weaver Cloud", "16.0", "PaaS", "Production", 5, "", 260000),
    ("SystemSoftware", "Application Server", "Zebra Middleware", "8.5", "On-premises", "Phase Out", 4, "2027-09-30", 210000),
    ("SystemSoftware", "Server Operating System 2016", "Aardvark OS", "2016.0", "On-premises", "Retiring", 4, "2027-01-12", 120000),
    ("SystemSoftware", "Server Operating System 2022", "Aardvark OS", "2022.0", "On-premises", "Production", 4, "", 140000),
    ("SystemSoftware", "Linux Server Platform", "Bontebok Linux", "9.4", "IaaS", "Production", 4, "", 90000),
    ("SystemSoftware", "Message Broker", "Jacana Integration", "3.6", "PaaS", "Production", 4, "", 110000),
    ("SystemSoftware", "Web Server", "Caracal Web", "2.4", "IaaS", "Production", 3, "", 30000),
    ("SystemSoftware", "Analytics Engine", "Kudu Data", "3.5", "PaaS", "Production", 3, "", 160000),
]
for t, name, vendor, version, hosting, life, crit, retire, cost in TECH:
    attrs = dict(Owner="Head of Infrastructure", Vendor=vendor, Version=version, Lifecycle=life, Criticality=crit,
                 ArchitectureState="Target" if life in ("Production",) and hosting != "On-premises" else "Baseline")
    if t in ("Node", "SystemSoftware"):
        attrs.update(Hosting=hosting, AnnualCost=cost)
        if retire:
            attrs["RetirementDate"] = retire
    ent(t, name, f"Technology: {name}", **attrs)
for name, vendor, version, life in [("Storage Array", "Vervet Hardware", "8.0", "Phase Out"),
                                    ("Branch Router", "Duiker Networks", "17.3", "Production"),
                                    ("Contact Centre Headsets", "Mamba Voice", "2.1", "Production")]:
    ent("Device", name, f"Device: {name}", Owner="Head of Infrastructure", Vendor=vendor, Version=version, Lifecycle=life,
        Criticality=3)
ent("Equipment", "Backup Generator", "Standby power at the primary data centre", Owner="Facilities", Vendor="Eland Power",
    Version="1.0", Lifecycle="Production", Criticality=4)
ent("Facility", "Primary Data Centre", "Leased data centre in Johannesburg", Owner="Facilities", Vendor="Flamingo Hosting",
    Version="1.0", Lifecycle="Phase Out", Criticality=5)
ent("CommunicationNetwork", "Corporate WAN", "Network linking offices and the data centre", Owner="Head of Infrastructure",
    Lifecycle="Production")
ent("CommunicationNetwork", "Cloud Interconnect", "Private link to the cloud provider", Owner="Head of Infrastructure",
    Lifecycle="Production")
ent("TechnologyInterface", "Cloud Management API", "The cloud provider's management interface", Owner="Head of Infrastructure",
    Lifecycle="Production")
for name, crit in [("Database Hosting Service", 5), ("Container Hosting Service", 5), ("Backup Service", 4),
                   ("Network Service", 4)]:
    ent("Service", name, f"Technology service: {name.lower()}", Owner="Head of Infrastructure", Domain="Technology",
        Criticality=crit, Lifecycle="Production")
for name in ["Policy Administration Release 10.2", "Claims Integration Package", "Billing Batch Jobs", "Customer Portal Build"]:
    ent("Artifact", name, f"Deployable artifact: {name}", Owner="Head of Infrastructure")
for name in ["Cape Town Head Office", "Johannesburg Operations Centre", "Durban Contact Centre", "Cloud Region Johannesburg"]:
    ent("Location", name, f"Location: {name}", Owner="Facilities")
ent("Grouping", "Digital Channels", "Everything customers and brokers use directly", Owner="Head of Digital")

# implementation and migration
for name, start, end, pr in [("Claims Digitisation Programme", "2026-01-15", "2027-06-30", "Must"),
                             ("Core Policy Replacement", "2026-04-01", "2028-06-30", "Must"),
                             ("Cloud Migration", "2026-02-01", "2028-03-31", "Must"),
                             ("Customer Data Programme", "2026-07-01", "2027-12-31", "Should"),
                             ("Broker API Project", "2026-05-01", "2026-12-15", "Should"),
                             ("Data Warehouse Decommission", "2027-01-01", "2027-09-30", "Could")]:
    ent("WorkPackage", name, f"Work package: {name}", Owner="Programme Office", Priority=pr, StartDate=start, EndDate=end)
for name, start, end in [("Online Claims Release", "2026-09-01", "2026-12-31"),
                         ("Cloud Policy Platform Live", "2027-01-01", "2027-03-31"),
                         ("Customer Master Data Live", "2026-10-01", "2026-12-31"),
                         ("Broker API Live", "2026-10-01", "2026-12-15"),
                         ("Data Centre Exit", "2028-01-01", "2028-03-31")]:
    ent("Deliverable", name, f"Deliverable: {name}", Owner="Programme Office", StartDate=start, EndDate=end)
for name, start, end, state in [("Baseline 2026", "2026-01-01", "2026-12-31", "Baseline"),
                                ("Transition 2027", "2027-01-01", "2027-12-31", "Transition"),
                                ("Target 2028", "2028-01-01", "2028-12-31", "Target")]:
    ent("Plateau", name, f"Plateau: {name}", Owner="Architecture Board", StartDate=start, EndDate=end, ArchitectureState=state)
ent("Event", "Programme Approved", "The board approved the transformation programme", Owner="Programme Office",
    Domain="Business")

# ---------------------------------------------------------------- relationships (source, type, target)
R: list[tuple[str, str, str]] = []


def rel(src: str, kind: str, *targets: str) -> None:
    for t in targets:
        R.append((src, kind, t))


# motivation chains
rel("Chief Executive", "Association", "Digital customer expectations", "Cost pressure")
rel("Chief Information Officer", "Association", "Ageing core systems", "Cyber threats")
rel("Chief Financial Officer", "Association", "Cost pressure")
rel("Chief Risk Officer", "Association", "Regulatory change", "Cyber threats")
rel("Prudential Regulator", "Association", "Regulatory change")
rel("Policyholders", "Association", "Digital customer expectations")
rel("Brokers", "Association", "Digital customer expectations")
rel("Digital customer expectations", "Association", "Claims take 21 days to settle", "Customer data held in nine places")
rel("Cost pressure", "Association", "Expense ratio 34%")
rel("Ageing core systems", "Association", "Three platforms past end of support")
rel("Claims take 21 days to settle", "Influence", "Settle claims faster")
rel("Expense ratio 34%", "Influence", "Lower the cost to serve")
rel("Three platforms past end of support", "Influence", "Modernise the core")
rel("Customer data held in nine places", "Influence", "Grow digital sales")
rel("Regulatory change", "Influence", "Stay compliant")
rel("Cyber threats", "Influence", "Stay compliant")
rel("Online first notice of loss", "Realization", "Settle claims faster")
rel("Straight-through underwriting", "Realization", "Grow digital sales", "Lower the cost to serve")
rel("One customer record", "Realization", "Grow digital sales")
rel("Cloud-hosted core", "Realization", "Modernise the core", "Lower the cost to serve")
rel("Cloud first", "Realization", "Modernise the core")
rel("Buy before build", "Realization", "Lower the cost to serve")
rel("Data is an asset", "Realization", "Stay compliant")
rel("Secure by design", "Realization", "Stay compliant")
rel("API first", "Realization", "Grow digital sales")
rel("Customers can lodge claims online", "Realization", "Online first notice of loss")
rel("Policies can be bought online", "Realization", "Straight-through underwriting")
rel("Personal information is protected", "Realization", "Data is an asset", "Secure by design")
rel("Claims are paid within 48 hours of approval", "Realization", "Settle claims faster")
rel("Brokers can quote through an API", "Realization", "API first")
rel("Single sign-on for staff", "Realization", "Secure by design")
rel("Regulatory returns produced automatically", "Realization", "Stay compliant")
rel("Core systems hosted in the cloud", "Realization", "Cloud first", "Cloud-hosted core")
rel("Claims Platform", "Realization", "Customers can lodge claims online")
rel("Customer Portal", "Realization", "Customers can lodge claims online", "Policies can be bought online")
rel("Payments Hub", "Realization", "Claims are paid within 48 hours of approval")
rel("Broker API Gateway", "Realization", "Brokers can quote through an API")
rel("Identity and Access Management", "Realization", "Single sign-on for staff", "Personal information is protected")
rel("Regulatory Reporting Tool", "Realization", "Regulatory returns produced automatically")
rel("Cloud Policy Platform", "Realization", "Core systems hosted in the cloud")
rel("Faster payouts", "Association", "Claims Service")
rel("Lower premiums", "Association", "Motor Cover", "Home Cover")
rel("Peace of mind", "Association", "Funeral Plan", "Life Cover")

# strategy
rel("Digitise claims", "Realization", "Settle claims faster", "Online first notice of loss")
rel("Move the core to the cloud", "Realization", "Modernise the core", "Cloud-hosted core")
rel("Build a single customer view", "Realization", "One customer record")
rel("Open up to brokers through APIs", "Realization", "Grow digital sales")
rel("Claims Management", "Realization", "Digitise claims")
rel("Technology Management", "Realization", "Move the core to the cloud")
rel("Customer Management", "Realization", "Build a single customer view")
rel("Sales and Distribution", "Realization", "Open up to brokers through APIs")
rel("Skilled claims assessors", "Assignment", "Claims Assessment")
rel("Actuarial team", "Assignment", "Pricing", "Actuarial Valuation")
rel("Customer data", "Assignment", "Customer Insight")
rel("Broker network", "Assignment", "Broker Management")
CAP_VS = {"Acquire a Customer: Attract": ["Direct Sales", "Broker Management", "Customer Insight"],
          "Acquire a Customer: Quote": ["Quoting", "Pricing", "Risk Assessment"],
          "Acquire a Customer: Buy": ["Policy Issue", "Billing and Collections"],
          "Acquire a Customer: Onboard": ["Customer Onboarding", "Data Protection"],
          "Settle a Claim: Lodge": ["Claims Lodgement", "Customer Service"],
          "Settle a Claim: Assess": ["Claims Assessment", "Fraud Detection"],
          "Settle a Claim: Approve": ["Claims Assessment", "Compliance Monitoring"],
          "Settle a Claim: Pay": ["Claims Settlement", "Financial Accounting"],
          "Renew a Policy: Remind": ["Renewals", "Customer Service"],
          "Renew a Policy: Review": ["Risk Assessment", "Pricing"],
          "Renew a Policy: Renew": ["Renewals", "Billing and Collections", "Policy Servicing"]}
for stage, caps in CAP_VS.items():
    for c in caps:
        rel(c, "Serving", stage)
for vs, stages in VSTREAMS.items():
    rel(vs, "Composition", *[f"{vs}: {s}" for s in stages])
    for a, b in zip(stages, stages[1:], strict=False):
        rel(f"{vs}: {a}", "Flow", f"{vs}: {b}")
# D345: lifecycle stages, scenarios, controls, contracts, measures
for prod in ("Motor Cover", "Funeral Plan"):
    rel(prod, "Composition", *[f"{prod}: {st}" for st, *_ in LIFECYCLE])
    for (a, *_), (b, *_) in zip(LIFECYCLE, LIFECYCLE[1:], strict=False):
        rel(f"{prod}: {a}", "Triggering", f"{prod}: {b}")
rel("Claim lodged online after a hailstorm", "Influence", "Settle claims faster", "Online first notice of loss")
rel("Claim lodged online after a hailstorm", "Association", "Policyholders", "Lodge Claim", "Claims Department")
rel("Broker binds cover through an API", "Influence", "Grow digital sales")
rel("Broker binds cover through an API", "Association", "Brokers", "Quote Policy", "Broker Management")
rel("Four-eyes approval of large claims", "Influence", "Approve Claim")
rel("Sanctions screening at onboarding", "Influence", "Onboard Customer")
rel("Premium reconciliation each month", "Influence", "Collect Premium")
rel("Cloud hosting agreement", "Association", "Cloud Landing Zone")
rel("Policy administration licence", "Association", "Policy Administration System")
rel("Repairer panel agreement", "Association", "Claims Settlement")
rel("Days to settle a claim", "Influence", "Online first notice of loss")
rel("Share of claims lodged online", "Influence", "Online first notice of loss")
rel("Expense ratio", "Association", "Lower the cost to serve")

# business
for actor, roles in {"Claims Department": ["Claims Assessor"], "Underwriting Department": ["Underwriter"],
                     "Sales Department": ["Sales Agent"], "Customer Contact Centre": ["Contact Centre Agent"],
                     "Finance Department": ["Actuary", "Finance Clerk"], "Risk and Compliance Office": ["Compliance Officer"],
                     "IT Department": ["Data Steward"]}.items():
    rel(actor, "Assignment", *roles)
rel("Claims Fraud Panel", "Aggregation", "Claims Assessor", "Compliance Officer")
rel("Claims Fraud Panel", "Assignment", "Detect Fraud")
ROLE_PROC = {"Claims Assessor": ["Assess Claim", "Approve Claim"], "Contact Centre Agent": ["Lodge Claim", "Change Policy"],
             "Finance Clerk": ["Pay Claim", "Collect Premium", "Close Financial Period"], "Underwriter": ["Underwrite Policy"],
             "Sales Agent": ["Quote Policy", "Issue Policy", "Onboard Customer"], "Actuary": ["Value Liabilities"],
             "Compliance Officer": ["Produce Regulatory Return"], "Policyholder": ["Lodge Claim", "Renew Policy"],
             "Broker": ["Quote Policy"]}
for role, procs in ROLE_PROC.items():
    rel(role, "Assignment", *procs)
for f, actor in [("Claims Handling", "Claims Department"), ("Underwriting Operations", "Underwriting Department"),
                 ("Billing", "Finance Department"), ("Customer Servicing", "Customer Contact Centre"),
                 ("Actuarial Work", "Finance Department"), ("Financial Control", "Finance Department")]:
    rel(actor, "Assignment", f)
for f, procs in {"Claims Handling": ["Lodge Claim", "Assess Claim", "Approve Claim", "Pay Claim"],
                 "Underwriting Operations": ["Quote Policy", "Underwrite Policy", "Issue Policy"],
                 "Billing": ["Collect Premium"], "Customer Servicing": ["Change Policy", "Renew Policy", "Onboard Customer"],
                 "Financial Control": ["Close Financial Period", "Produce Regulatory Return"],
                 "Actuarial Work": ["Value Liabilities"]}.items():
    rel(f, "Serving", *procs)
rel("Lodge Claim", "Triggering", "Assess Claim")
rel("Assess Claim", "Triggering", "Approve Claim")
rel("Approve Claim", "Triggering", "Pay Claim")
rel("Assess Claim", "Triggering", "Detect Fraud")
rel("Quote Policy", "Triggering", "Underwrite Policy")
rel("Underwrite Policy", "Triggering", "Issue Policy")
rel("Issue Policy", "Triggering", "Collect Premium")
rel("First Notice of Loss", "Triggering", "Lodge Claim")
rel("Policy Renewal Due", "Triggering", "Renew Policy")
rel("Month End", "Triggering", "Close Financial Period")
rel("Premium Missed", "Triggering", "Collect Premium")
for proc, svc in [("Lodge Claim", "Claims Service"), ("Pay Claim", "Claims Service"), ("Issue Policy", "Policy Purchase Service"),
                  ("Change Policy", "Policy Servicing Service"), ("Collect Premium", "Premium Collection Service"),
                  ("Onboard Customer", "Customer Support Service"), ("Quote Policy", "Broker Quoting Service"),
                  ("Produce Regulatory Return", "Regulatory Reporting Service"), ("Detect Fraud", "Fraud Screening Service")]:
    rel(proc, "Realization", svc)
rel("Claims Service", "Serving", "Policyholder", "Broker")
rel("Policy Purchase Service", "Serving", "Policyholder", "Broker")
rel("Policy Servicing Service", "Serving", "Policyholder")
rel("Broker Quoting Service", "Serving", "Broker")
rel("Regulatory Reporting Service", "Serving", "Risk and Compliance Office")
rel("Contact Centre Line", "Assignment", "Customer Support Service", "Claims Service")
rel("Branch Counter", "Assignment", "Policy Purchase Service")
rel("Broker Desk", "Assignment", "Broker Quoting Service")
rel("Customer Contact Centre", "Composition", "Contact Centre Line")
rel("Sales Department", "Composition", "Broker Desk", "Branch Counter")
PROC_BO = {"Lodge Claim": ["Claim", "Policy"], "Assess Claim": ["Claim", "Medical Report"], "Pay Claim": ["Claim"],
           "Quote Policy": ["Quote", "Customer"], "Issue Policy": ["Policy", "Customer"], "Collect Premium": ["Premium"],
           "Onboard Customer": ["Customer"], "Produce Regulatory Return": ["Regulatory Return"],
           "Renew Policy": ["Policy", "Premium"], "Detect Fraud": ["Claim"], "Underwrite Policy": ["Policy", "Medical Report"]}
for proc, objs in PROC_BO.items():
    rel(proc, "Access", *objs)
for prod, svcs in {"Motor Cover": ["Claims Service", "Policy Servicing Service"], "Home Cover": ["Claims Service"],
                   "Funeral Plan": ["Claims Service", "Premium Collection Service"],
                   "Life Cover": ["Claims Service", "Policy Servicing Service"], "Business Cover": ["Broker Quoting Service"]}.items():
    rel(prod, "Aggregation", *svcs, "Policy")
rel("Claims Platform", "Realization", "Claims Lodgement", "Claims Assessment", "Claims Settlement")
rel("Fraud Analytics", "Realization", "Fraud Detection")
rel("Policy Administration System", "Realization", "Policy Servicing", "Policy Issue", "Renewals")
rel("Cloud Policy Platform", "Realization", "Policy Servicing", "Policy Issue", "Renewals")
rel("Billing Engine", "Realization", "Billing and Collections")
rel("Payments Hub", "Realization", "Claims Settlement", "Billing and Collections")
rel("General Ledger", "Realization", "Financial Accounting")
rel("Actuarial Modelling", "Realization", "Actuarial Valuation", "Pricing")
rel("Regulatory Reporting Tool", "Realization", "Regulatory Reporting")
rel("Customer Portal", "Realization", "Direct Sales", "Customer Service", "Claims Lodgement")
rel("Mobile App", "Realization", "Direct Sales", "Claims Lodgement")
rel("Broker Portal", "Realization", "Broker Management", "Quoting")
rel("Broker API Gateway", "Realization", "Broker Management", "Quoting")
rel("Customer Master Data Hub", "Realization", "Customer Insight", "Customer Onboarding")
rel("CRM", "Realization", "Customer Service", "Customer Insight", "Direct Sales")
rel("Contact Centre Telephony", "Realization", "Customer Service")
rel("Document Management", "Realization", "Policy Servicing")
rel("Data Warehouse", "Realization", "Customer Insight", "Regulatory Reporting", "Data Management")
rel("Cloud Data Platform", "Realization", "Customer Insight", "Data Management")
rel("Underwriting Rules Engine", "Realization", "Risk Assessment")
rel("Quote Engine", "Realization", "Quoting", "Pricing")
rel("Identity and Access Management", "Realization", "Security Management")
rel("Security Monitoring", "Realization", "Security Management", "Risk Management")
rel("Reinsurance Administration", "Realization", "Reinsurance")
rel("Complaints Tracker", "Realization", "Compliance Monitoring")
rel("Email Campaigns", "Realization", "Direct Sales")
rel("Claims Platform", "Serving", "Claims Department")
rel("CRM", "Serving", "Customer Contact Centre", "Sales Department")
rel("Policy Administration System", "Serving", "Underwriting Department")
rel("General Ledger", "Serving", "Finance Department")
rel("Regulatory Reporting Tool", "Serving", "Risk and Compliance Office")
rel("HR System", "Serving", "Executive Committee")
rel("Broker Portal", "Serving", "Broker")
rel("Customer Portal", "Serving", "Policyholder")
rel("Contact Centre Telephony", "Serving", "Contact Centre Agent")
rel("Claims Platform", "Assignment", "Validate Claim")
rel("Quote Engine", "Assignment", "Calculate Premium")
rel("Fraud Analytics", "Assignment", "Score Fraud Risk")
rel("Document Management", "Assignment", "Generate Policy Documents")
rel("Validate Claim", "Serving", "Assess Claim")
rel("Calculate Premium", "Serving", "Quote Policy")
rel("Score Fraud Risk", "Serving", "Detect Fraud")
rel("Generate Policy Documents", "Serving", "Issue Policy")
APP_IF = {"Policy Administration System": "Policy API", "Claims Platform": "Claims API", "Payments Hub": "Payments API",
          "Customer Master Data Hub": "Customer API", "Broker API Gateway": "Broker Quote API",
          "General Ledger": "Ledger File Interface"}
for app, iface in APP_IF.items():
    rel(app, "Composition", iface)
for iface, svc in [("Policy API", "Policy Data Service"), ("Claims API", "Claims Data Service"), ("Payments API", "Payment Service"),
                   ("Customer API", "Customer Data Service"), ("Broker Quote API", "Quote Calculation Service")]:
    rel(iface, "Assignment", svc)
rel("Policy Data Service", "Serving", "Issue Policy", "Change Policy", "Renew Policy")
rel("Claims Data Service", "Serving", "Lodge Claim", "Assess Claim")
rel("Payment Service", "Serving", "Pay Claim", "Collect Premium")
rel("Customer Data Service", "Serving", "Onboard Customer")
rel("Quote Calculation Service", "Serving", "Quote Policy")
rel("Fraud Scoring Service", "Serving", "Detect Fraud")
rel("Reporting Data Service", "Serving", "Produce Regulatory Return")
rel("Identity Service", "Serving", "Customer Portal", "Mobile App", "Broker Portal", "CRM")
rel("Score Fraud Risk", "Realization", "Fraud Scoring Service")
rel("Identity and Access Management", "Association", "Identity Service")
rel("Data Warehouse", "Association", "Reporting Data Service")
# application flows and serving (integration)
FLOWS = [("Customer Portal", "Claims Platform"), ("Mobile App", "Claims Platform"), ("Customer Portal", "Policy Administration System"),
         ("Claims Platform", "Payments Hub"), ("Claims Platform", "Fraud Analytics"), ("Claims Platform", "Document Management"),
         ("Policy Administration System", "Billing Engine"), ("Billing Engine", "Payments Hub"), ("Payments Hub", "General Ledger"),
         ("Billing Engine", "General Ledger"), ("Policy Administration System", "Data Warehouse"), ("Claims Platform", "Data Warehouse"),
         ("Data Warehouse", "Regulatory Reporting Tool"), ("General Ledger", "Regulatory Reporting Tool"),
         ("Actuarial Modelling", "Regulatory Reporting Tool"), ("Data Warehouse", "Actuarial Modelling"),
         ("Broker Portal", "Quote Engine"), ("Broker API Gateway", "Quote Engine"), ("Quote Engine", "Underwriting Rules Engine"),
         ("Quote Engine", "Policy Administration System"), ("CRM", "Customer Master Data Hub"),
         ("Customer Master Data Hub", "Policy Administration System"), ("Customer Master Data Hub", "Claims Platform"),
         ("Policy Administration System", "Reinsurance Administration"), ("Claims Platform", "Reinsurance Administration"),
         ("Cloud Policy Platform", "Billing Engine"), ("Cloud Policy Platform", "Cloud Data Platform"),
         ("Claims Platform", "Cloud Data Platform"), ("Cloud Data Platform", "Regulatory Reporting Tool"),
         ("CRM", "Email Campaigns"), ("Complaints Tracker", "CRM")]
for a, b in FLOWS:
    rel(a, "Flow", b)
for app in ["Customer Portal", "Mobile App", "Broker Portal", "Broker API Gateway", "Claims Platform", "Policy Administration System",
            "Billing Engine", "Payments Hub", "CRM", "Cloud Policy Platform"]:
    rel("Integration Platform", "Serving", app)
APP_DATA = {"Policy Administration System": ["Policy Record", "Customer Record", "Policy Document"],
            "Cloud Policy Platform": ["Policy Record", "Customer Record"],
            "Claims Platform": ["Claim Record", "Policy Record", "Customer Record"],
            "Fraud Analytics": ["Fraud Score", "Claim Record"], "Billing Engine": ["Premium Record", "Policy Record"],
            "Payments Hub": ["Payment Instruction"], "General Ledger": ["General Ledger Entry"],
            "Regulatory Reporting Tool": ["Regulatory Return File", "General Ledger Entry"],
            "Customer Portal": ["Customer Record", "Claim Record", "Quote Record"], "Quote Engine": ["Quote Record"],
            "Broker Portal": ["Quote Record", "Broker Record"], "Broker API Gateway": ["Quote Record"],
            "Customer Master Data Hub": ["Customer Record"], "CRM": ["Customer Record", "Broker Record"],
            "Data Warehouse": ["Policy Record", "Claim Record", "Premium Record", "Customer Record", "Actuarial Data Set"],
            "Cloud Data Platform": ["Policy Record", "Claim Record", "Customer Record", "Actuarial Data Set"],
            "Actuarial Modelling": ["Actuarial Data Set"], "Document Management": ["Policy Document"],
            "Reinsurance Administration": ["Policy Record", "Claim Record"]}
for app, objs in APP_DATA.items():
    rel(app, "Access", *objs)
for do, bo in [("Policy Record", "Policy"), ("Claim Record", "Claim"), ("Customer Record", "Customer"),
               ("Premium Record", "Premium"), ("Quote Record", "Quote"), ("Regulatory Return File", "Regulatory Return"),
               ("Broker Record", "Broker Agreement")]:
    rel(do, "Realization", bo)

# technology
rel("Primary Data Centre Cluster", "Composition", "Relational Database 12", "Relational Database 19", "Application Server",
    "Server Operating System 2016", "Storage Array")
rel("Disaster Recovery Cluster", "Composition", "Relational Database 19", "Server Operating System 2022")
rel("Cloud Landing Zone", "Composition", "Container Platform", "Managed Cloud Database", "Linux Server Platform", "Analytics Engine")
rel("Container Platform", "Composition", "Message Broker", "Web Server")
rel("Cloud Landing Zone", "Composition", "Cloud Management API")
TECH_APP = {"Relational Database 12": ["Billing Engine", "Reinsurance Administration", "Complaints Tracker"],
            "Relational Database 19": ["Policy Administration System", "Data Warehouse", "Regulatory Reporting Tool",
                                       "Document Management", "Quote Engine"],
            "Application Server": ["Policy Administration System", "Broker Portal", "Underwriting Rules Engine"],
            "Mainframe Partition": ["Billing Engine"],
            "Server Operating System 2016": ["Regulatory Reporting Tool", "Complaints Tracker", "Reinsurance Administration"],
            "Container Platform": ["Customer Portal", "Mobile App", "Broker API Gateway", "Integration Platform"],
            "Managed Cloud Database": ["Customer Portal", "Cloud Data Platform", "Payments Hub"],
            "Linux Server Platform": ["Actuarial Modelling", "Quote Engine"],
            "Message Broker": ["Integration Platform"], "Analytics Engine": ["Cloud Data Platform", "Fraud Analytics"],
            "Web Server": ["Customer Portal"]}
for tech, apps in TECH_APP.items():
    rel(tech, "Serving", *apps)
rel("Primary Data Centre Cluster", "Serving", "Policy Administration System", "Billing Engine", "Data Warehouse")
rel("Cloud Landing Zone", "Serving", "Customer Portal", "Cloud Data Platform")
rel("Cloud Management API", "Serving", "Container Platform")
rel("Primary Data Centre Cluster", "Assignment", "Policy Administration Release 10.2", "Billing Batch Jobs")
rel("Container Platform", "Assignment", "Claims Integration Package", "Customer Portal Build")
rel("Policy Administration Release 10.2", "Realization", "Policy Administration System")
rel("Customer Portal Build", "Realization", "Customer Portal")
rel("Container Platform", "Association", "Container Hosting Service")
rel("Managed Cloud Database", "Association", "Database Hosting Service")
rel("Relational Database 19", "Association", "Database Hosting Service")
rel("Container Hosting Service", "Serving", "Customer Portal", "Mobile App", "Broker API Gateway")
rel("Database Hosting Service", "Serving", "Policy Administration System", "Claims Platform", "Data Warehouse")
rel("Backup Service", "Serving", "Policy Administration System", "General Ledger")
rel("Network Service", "Serving", "Primary Data Centre Cluster", "Cloud Landing Zone")
rel("Corporate WAN", "Association", "Primary Data Centre Cluster", "Branch Router")
rel("Cloud Interconnect", "Association", "Cloud Landing Zone", "Primary Data Centre Cluster")
rel("Primary Data Centre", "Association", "Primary Data Centre Cluster", "Backup Generator", "Storage Array")
rel("Cape Town Head Office", "Aggregation", "Executive Committee", "Underwriting Department", "Finance Department",
    "Risk and Compliance Office")
rel("Johannesburg Operations Centre", "Aggregation", "Claims Department", "Sales Department", "IT Department",
    "Primary Data Centre", "Primary Data Centre Cluster")
rel("Durban Contact Centre", "Aggregation", "Customer Contact Centre", "Contact Centre Headsets")
rel("Cloud Region Johannesburg", "Aggregation", "Cloud Landing Zone", "Container Platform", "Managed Cloud Database")
rel("Digital Channels", "Aggregation", "Customer Portal", "Mobile App", "Broker Portal", "Broker API Gateway")

# implementation and migration
rel("Claims Digitisation Programme", "Realization", "Online Claims Release")
rel("Core Policy Replacement", "Realization", "Cloud Policy Platform Live")
rel("Customer Data Programme", "Realization", "Customer Master Data Live")
rel("Broker API Project", "Realization", "Broker API Live")
rel("Cloud Migration", "Realization", "Data Centre Exit")
rel("Online Claims Release", "Realization", "Mobile App", "Claims Platform")
rel("Cloud Policy Platform Live", "Realization", "Cloud Policy Platform")
rel("Customer Master Data Live", "Realization", "Customer Master Data Hub")
rel("Broker API Live", "Realization", "Broker API Gateway")
rel("Data Centre Exit", "Realization", "Cloud Landing Zone", "Cloud Data Platform")
rel("Online Claims Release", "Realization", "Transition 2027")
rel("Cloud Policy Platform Live", "Realization", "Transition 2027")
rel("Data Centre Exit", "Realization", "Target 2028")
rel("Baseline 2026", "Triggering", "Transition 2027")
rel("Transition 2027", "Triggering", "Target 2028")
rel("Baseline 2026", "Aggregation", "Policy Administration System", "Billing Engine", "Data Warehouse", "Broker Portal",
    "Claims Platform", "Primary Data Centre Cluster", "Relational Database 12")
rel("Transition 2027", "Aggregation", "Cloud Policy Platform", "Policy Administration System", "Claims Platform",
    "Customer Master Data Hub", "Broker API Gateway", "Cloud Data Platform", "Primary Data Centre Cluster")
rel("Target 2028", "Aggregation", "Cloud Policy Platform", "Claims Platform", "Customer Master Data Hub", "Broker API Gateway",
    "Cloud Data Platform", "Cloud Landing Zone")
rel("Programme Approved", "Triggering", "Claims Digitisation Programme")
rel("Claims Digitisation Programme", "Triggering", "Cloud Migration")
rel("Customer Data Programme", "Triggering", "Data Warehouse Decommission")
rel("IT Department", "Assignment", "Cloud Migration", "Data Warehouse Decommission", "Broker API Project")
rel("Claims Department", "Assignment", "Claims Digitisation Programme")
rel("Underwriting Department", "Assignment", "Core Policy Replacement")
rel("Claims Digitisation Programme", "Association", "Customers can lodge claims online", "Digitise claims")
rel("Core Policy Replacement", "Association", "Core systems hosted in the cloud", "Move the core to the cloud")
rel("Customer Data Programme", "Association", "Build a single customer view")
rel("Broker API Project", "Association", "Open up to brokers through APIs")

_names = [n for _t, n, *_ in E]
assert len(_names) == len(set(_names)), sorted({n for n in _names if _names.count(n) > 1})
_known = set(_names)
_bad = [(a, b) for a, _k, b in R if a not in _known or b not in _known]
assert not _bad, _bad
