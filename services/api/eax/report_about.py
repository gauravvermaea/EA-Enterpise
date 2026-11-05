"""The "About this report" section at the top of every report (owner, 5 Nov 2026, D186): what it shows, how to use it
and how to read it. Specific text for the standard, gap and dependency
reports; the TOGAF catalogues and matrices, viewpoints and audience dashboards share a text per family, filled in with the
report's own subject.

about(report) -> {"use": ..., "read": ...}
"""

from __future__ import annotations

G: dict[str, tuple[str, str]] = {
    "MO": ("Start here to see what a model holds and how actively it is being changed, before opening a specific report.",
           "Large counts show where the model is detailed; types with few or no entities are gaps in coverage. The recent "
           "changes show whether the model is being kept up to date: no changes for months usually means stale content."),
    "SR-01": ("Use it to review the application portfolio with owners: who owns what, what it costs, how critical it is and its "
              "TIME classification. Filter by lifecycle or owner and export it as the portfolio inventory.",
              "Look for applications with no owner, no cost or no TIME: those are the data to complete first. High cost with "
              "Tolerate or Eliminate is where savings usually are; Invest with low criticality deserves a question."),
    "SR-02": ("Use it to agree the capability map with the business and to see which capabilities have support.",
              "Each level is a step down the capability tree. Capabilities with no applications are unsupported or done by "
              "hand; many applications on one capability point to overlap (see SR-25). Low maturity on a critical capability "
              "is a candidate for investment."),
    "SR-03": ("Use it to keep the technology inventory current and plan upgrades.",
              "Check the end-of-life dates: anything past or within the next year needs a plan (see SR-17 and SR-23). Missing "
              "versions or vendors mean the inventory cannot support support-contract or risk decisions yet."),
    "SR-04": ("Use it with data owners to agree the data entities, their owners and classification.",
              "Every data entity should have an owner and a classification; restricted and confidential data without an owner "
              "is a governance risk. Compare with SR-11 to see which applications touch each entity."),
    "SR-05": ("Use it to agree the process landscape and who performs each process.",
              "Processes with no role are unassigned work; a role on very many processes may be a bottleneck. Levels show how "
              "deep the process model goes in each area."),
    "SR-06": ("Use it to review integrations: what flows from which application to which, before a change to either end.",
              "Each row is a link from source to target. Many links on one application make it a hub whose change ripples "
              "widely; an interface with no flows may be unused."),
    "SR-07": ("Use it to list who is involved: actors, roles, collaborations and stakeholders, for engagement planning.",
              "Stakeholders with no concerns recorded, and actors with no role, are the ones to follow up."),
    "SR-08": ("Use it to trace why the architecture exists: drivers, goals, outcomes, principles and requirements.",
              "Goals with no outcome and requirements with nothing realising them are open intentions; drivers with no goal "
              "have not been acted on."),
    "SR-09": ("Use it to see which applications support each capability, for rationalisation and impact questions.",
              "A filled cell means the application supports the capability. Rows with many cells are broad platforms; "
              "columns with many cells are capabilities with overlap; empty columns are unsupported capabilities."),
    "SR-10": ("Use it to see which applications serve each process.",
              "Read across a process for the systems it needs; read down an application for the processes that stop if it "
              "stops. Empty rows are manual processes."),
    "SR-11": ("Use it to find which applications create, read, update or delete each data entity (CRUD).",
              "Each cell holds the access type. More than one application creating the same entity means more than one "
              "master: a data quality risk. An entity only read, never created, comes from outside the model."),
    "SR-12": ("Use it to see the technology each application runs on, for upgrade and hosting decisions.",
              "Read down a technology for every application affected when it changes or reaches end of life."),
    "SR-13": ("Use it to see who performs or owns each process.",
              "Processes with no role are unowned; one role across many processes may need support."),
    "SR-14": ("Use it to see which capabilities enable each stage of a value stream.",
              "A stage with no capability is not supported by the architecture; a capability on many stages is critical to "
              "the value delivered."),
    "SR-15": ("Use it to see application-to-application flows in one grid.",
              "Each filled cell is a flow from the row application to the column one. Dense rows or columns are integration "
              "hubs; their change needs the most coordination."),
    "SR-16": ("Use it to show where capabilities are well or poorly supported, by applications, maturity and criticality.",
              "Colours follow the bands set in the filters (for example, green for enough support, red for none or too many). "
              "Red on a critical capability is the first to address; change the thresholds in the filter to suit your estate."),
    "SR-17": ("Use it to plan technology upgrades and replacements by end-of-life date.",
              "Rows past their end of life are red; those within the warning period you choose are amber. Plan the red ones "
              "now and the amber ones in the next budget cycle."),
    "SR-18": ("Use it to agree the TIME decision for each application: Tolerate, Invest, Migrate or Eliminate.",
              "High functional and high technical fit: Invest. High functional, low technical: Migrate. Low functional, high "
              "technical: Tolerate. Both low: Eliminate. Compare the quadrant with the TIME set on each application; "
              "disagreements are the ones to discuss."),
    "SR-19": ("Use it to find critical applications in poor technical health.",
              "Top left (high criticality, low technical fit) is the risk zone: critical to the business and fragile. Bubble "
              "size shows cost where it is known."),
    "SR-20": ("Use it to see what each capability costs, through the applications and technology that support it.",
              "Costs roll up from applications and technology; a capability with high cost and low maturity or value is a "
              "candidate for review. Missing costs make a capability look cheaper than it is."),
    "SR-21": ("Use it to see dependence on each vendor, for sourcing and risk discussions.",
              "A vendor with many applications or a large share of the cost is a concentration risk and a negotiation lever."),
    "SR-22": ("Use it before changing or retiring something: choose the entity in the filter to see everything that depends on it.",
              "Depth 1 is directly affected; higher depths are knock-on effects. The path shows how each dependant is reached."),
    "SR-23": ("Use it to find applications and capabilities at risk from technology at or near its end of life.",
              "Red is past end of life, amber within the warning period you choose. Critical applications in red are the "
              "first to remediate."),
    "SR-24": ("Use it to find single points of failure: items many others depend on.",
              "Items at the top have the most dependants; those with no alternative are the real single points of failure "
              "and need resilience or a backup plan."),
    "SR-25": ("Use it to find overlapping applications to rationalise.",
              "Capabilities with more than one application are candidates; compare the applications' fit, cost and TIME "
              "before deciding which to keep."),
    "SR-26": ("Use it to drive data quality: which types and owners have the most missing required values.",
              "Low completeness means reports on that type are unreliable. Send the list of entities missing values to their "
              "owners."),
    "SR-27": ("Use it to find entities that are not connected to anything.",
              "An orphan is often a duplicate, a leftover or an entity whose relationships were never captured; check each "
              "one and connect, merge or retire it."),
    "SR-28": ("Use it to find likely duplicates before they spread into reports.",
              "Pairs with a high similarity score are probably the same thing; open both and merge or rename."),
    "SR-29": ("Use it to see how actively models are maintained and by whom.",
              "Steady activity shows a living repository; long quiet periods or one person doing all changes are risks to "
              "currency and continuity."),
    "SR-30": ("Use it to see how a model has moved away from the model it was created from.",
              "Kept means unchanged, changed has different values, new was added here, removed was dropped. Large numbers of "
              "changes may mean the source should be updated too, or the copy merged back."),
    "HM": ("Use it to see how the values of each pick list (lifecycle, criticality, TIME...) are spread across entities.",
           "A value with very many entities, or many entities with no value, shows where the data needs attention; set the "
           "bands in the filters."),
    "GR-01": ("Use it to see every gap analysis, its baseline and target, and how much is still to decide.",
              "New and eliminated are the gaps to act on; changed shows what moves; undecided counts gaps with no resolution "
              "yet: drive it to zero before the migration plan is agreed. Open goes to the analysis in EA Explorer."),
    "GR-02": ("Use it to see where the gaps are, by layer and entity type.",
              "Large bars show the parts of the architecture that change most between baseline and target, and so where the "
              "work and the risk are."),
    "GR-03": ("Use it as the TOGAF gap matrix: baseline elements down, target elements across.",
              "A cell where an element appears on both sides is included (kept or changed); an element only in the "
              "baseline is eliminated (retire it, or add it back if it was dropped by accident); only in the target is new "
              "(build or buy it)."),
    "GR-04": ("Use it to follow the decisions on gaps: resolution and work packages.",
              "Gaps without a resolution are undecided; gaps with a resolution but no work package are decided but not "
              "planned. Both should be empty before the roadmap is final."),
    "GR-05": ("Use it to see the Gap entities in the models: the gaps recorded as part of the architecture.",
              "Each Gap entity names its status, resolution and the analysis it came from; filter by the analysis or result "
              "tag to see one result's gaps."),
    "DR-01": ("Choose an entity in the filter to see what it depends on and what depends on it.",
              "Upstream items can break it; downstream items break if it changes. The step count shows how far away each is."),
    "DR-02": ("Choose a row type and a column type to see every relationship between their entities.",
              "Filled cells are relationships; empty rows or columns are entities with no link to the other type."),
    "DR-03": ("Use it to trace each technology up to the value streams it ultimately supports.",
              "A technology that reaches many value streams is business-critical even if it looks small; change it with care."),
    "DR-04": ("Use it to find dependency hot spots.",
              "Entities with many dependants are hubs; with many dependencies, fragile. Set the bands in the filters."),
}

FAMILY: dict[str, tuple[str, str]] = {
    "TOGAF catalogue": ("Use it as the TOGAF {title}: the list to review with its owners and keep current, filtered by model.",
                        "Each row is one item with its key attributes; blanks are data to complete. Open goes to the item in EA "
                        "Explorer."),
    "TOGAF matrix": ("Use it as the TOGAF {title}: which items of one kind relate to which of another.",
                     "A filled cell is a relationship between the row and the column. Empty rows or columns are items with no "
                     "link to the other kind; very full rows or columns are hubs."),
    "Viewpoint": ("Use it to look at the model the way the {title} viewpoint's stakeholders need: only the element and "
                  "relationship types that matter to their concerns.",
                  "The catalog lists the elements, the relationships table shows how they connect, and the heat map colours "
                  "elements by the viewpoint's attribute. Missing elements of a type mean that part is not modelled yet."),
    "Audience": ("Use it as the starting dashboard for the {title}: the reports that matter to this audience, together.",
                 "Each chart is described where it comes from; open the full report from the Reports tab for detail."),
    "Gap analysis": ("Use it to follow gap analyses and their decisions.", "Read the counts by status and resolution."),
    "Dependency": ("Use the filters to choose what to analyse.", "Read the dependants and dependencies by step."),
    "Standard": ("Use it to review the model with its owners.", "Blank values are data to complete."),
}


def about(report: dict) -> dict[str, str]:
    """{"use": how to use the report, "read": how to read it}."""
    if report["code"] in G:
        use, read = G[report["code"]]
    else:
        use, read = FAMILY.get(report.get("family", "Standard"), FAMILY["Standard"])
    title = report.get("title", "")
    return {"use": use.format(title=title.lower() if report.get("family") == "TOGAF catalogue" else title),
            "read": read.format(title=title)}
