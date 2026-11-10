# Build phase 13.0.3: model roles and project templates as wizards

Goal: a project knows what each of its models is for (current state, target state, transition states, scenarios,
reference, working copy). People start a project from a template, a specialised wizard with the decisions already
taken, or from a blank project; either way every decision can still be changed.

- Version **0.14.3**, migration `0025_project_templates`.
- Decisions **D281** (model roles) and **D282** (project templates), agreed with the owner on 7 Nov 2026.
- Built on 13.0.1 (D274 to D280).

## Status: accepted and closed by the owner (8 Nov 2026, D323)

## What it delivers

### Model roles (D281)

Each model in a project has a role:

| Role | Meaning |
|---|---|
| **Current state** | How things are today |
| **Target state** | How things should be |
| **Transition state** | An intermediate state between current and target (TOGAF transition architectures), numbered 1, 2, … |
| **Scenario** | An alternative target for what-if, lettered A, B, … |
| **Reference** | Read for context only |
| **Working copy** | A copy to update and merge back |

- The role is chosen in the wizard (Models, and ✎ Edit). It shows next to the model on the project's Home and About
  tabs.
- **Gap analyses are not made by the wizard.** People make them on the gap screen when they need them (owner). When a
  project has a current state and a target, transition or scenario, About links to the gap screen.

### Project templates (D282)

**+ New project** opens a **gallery**: 14 kinds of project, plus **Blank project** (the full wizard). Choosing one
opens its wizard with its decisions already filled in:
- **Models:** one section per role the template asks for. Each section says how many models it needs and which ways
  they start (select existing; new: create empty, derive from an existing model, or derive and keep the parent-child
  link). New models start from the current-state model by default.
- **Primary working model:** chosen from the template's role (usually the target state).
- **Purpose and scope:** depth and domains.
- **Phases:** the deliverables and artifacts in use.
- **Views.**
- **Steps left out:** for example, no Goals step when the template has no goals.
- **The way it finishes:** shown as a hint.

**Both ways (owner):** the full wizard has a **Kind of project** choice at the top, which applies a template's
decisions to the wizard as it stands. Every decision stays editable, then and later with ✎ Edit.

**The 14 templates** (the owner's six, then those suggested and agreed):

| Template | Models (by role) | Goals into |
|---|---|---|
| Transformation | current, target (child), transitions, reference | target |
| Document the as-is | current, reference | none |
| Create a new product | reference, the new product's model (empty) | target |
| Copy a model for new reports | the copy (separate) | none |
| Copy, update and merge back | the working copy (child) | working copy |
| Scenario planning | current, two or more scenarios, reference | current |
| Regulatory or compliance change | current, target, reference | target |
| Technology refresh or cloud migration | current, target, transitions (waves), reference | target |
| Application rationalisation | current, target | target |
| Operating model redesign | current, target, transitions | target |
| Capability-based planning | current, target | target |
| Architecture assessment or health check | the models assessed (reference) | none |
| Solution architecture for one initiative | reference, the solution model (child) | solution model |
| Due diligence, merger or acquisition | two current states (ours and theirs), combined target | target |

**Templates are data:**
- They are shipped in `eax/seed/project_templates.json` and added once; a Super Admin's changes are kept.
- On **Administration › Project library › Project templates**, a Super Admin (or a Library Admin) changes a
  template's name, icon, description and its decisions (JSON), or retires and offers one again.
- **Save as a project template**, on a project, makes a new template from that project's decisions: its models by
  role and how each started (not the models themselves), purpose, scope, the deliverables in use, removed steps,
  views, and goals into which role.
- A project remembers the template it was made from, shown as a chip in its header.

## API

| Method | Route | What it does |
|---|---|---|
| GET | `/projects/templates` | The project templates (`?all=true` includes retired ones) |
| POST | `/projects/templates` | A new template |
| PUT | `/projects/templates/<code>` | Change or retire a template |
| POST | `/projects/<p>/as-template` | Save a project as a template |
| | `/projects/library` | Also gives `project_templates` and `model_roles` |
| | create and edit | Take `template`, and `role` and `seq` per model |

## How to check it (after `.\eax clean-restart`)

1. **+ New project:** the gallery shows 14 cards and Blank project.
2. **Transformation.**
   - Models: Current state › Select existing › Protea. Target state › + New model… › Derive and keep the parent-child
     link (Protea is filled in). Add a transition state.
   - Primary working model: the target is chosen.
   - The deliverables of every phase are ticked.
   - Create it. On Home and About each model shows its role, and About links to the gap screen.
3. **Document the as-is:** there is no Goals step, the primary working model is None, and only phases P to D are in use.
4. **Blank project:** set Kind of project to Scenario planning. Its decisions fill in, and you can still change them.
5. **✎ Edit:** change a transition into a scenario and save it. The role changes.
6. **As a Super Admin:**
   - On the project, **Save as a project template**: it appears in the gallery.
   - Administration › Project library › Project templates: retire one, and it leaves the gallery; offer it again.
   - Change a template's JSON: it is checked when saved (an unknown role is refused).

## Not in this phase

- Gap analyses made automatically (people make them on the gap screen).
- The templates' own deliverables (each uses the library's deliverables by phase; a template can name items instead).
- A form editor for a template's decisions (JSON for now).
