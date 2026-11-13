"""The top menu (R2.0, D586 to D590): nine areas, sub-menus for the wizards, and nothing left out (owner, 11 Nov 2026:
"Please ensure every feature is reachable", "Nothing is left out"); placed again at 21:41 (D591). Every page, tab and wizard the screens link to is
in the menu, or is opened from a page that is."""

import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[2] / "web" / "src"


def _src(name: str) -> str:
    return (WEB / name).read_text(encoding="utf-8")


MENU = _src("menu.js")
HREFS = set(re.findall(r'href: "(#/[^"]*)"', MENU))
PATHS = {h.split("?")[0].rstrip("/") for h in HREFS}

# reached from a page in the menu, not from the menu itself (with where from)
FROM_A_PAGE = {
    "#/break-glass": "the sign-in page, when Keycloak is down",
    "#/documentation": "one document, from Documentation (every document) and the Start page's Set up card",
    "#/drawio/open": "Open in draw.io on every picture (D585)",
    "#/change-documents": "the change log and notifications",
    "#/more": "Classic only (Everything else)",
    "#/notifications/requests": "one request, from Requests to me or I sent",
    "#/projects": "a project, from My projects (listed when opened) and Projects",
    "#/repository/reference": "the four reference architectures are in the menu by their full address",
}


def test_the_areas_and_where_they_sit():
    """D586, D591: the site picker (Farm Admin) on the left; Architecture Work, Model Admin, Project Admin, Repository and
    System Admin across the top; ? (help and documentation) and the person's own menu (User and Profile, Sign out) on
    the right."""
    keys = re.findall(r'\{ key: "([a-z]+)", label: "([^"]+)"(?:, title: "[^"]+")?(?:, place: "([a-z]+)")?', MENU)
    main = [label for _, label, place in keys if not place]
    assert main == ["Architecture Work", "Model Admin", "Project Admin", "Repository & Content Framework",
                    "System Admin"], keys
    # owner, 21:46: "Call it Reposiory & Content Framework"
    assert {k: place for k, _, place in keys if place} == {"me": "right", "help": "right", "farm": "left"}
    me = MENU[MENU.index('key: "me"'):MENU.index('key: "work"')]
    for x in ("Home", "My tasks", "My profile and skills", "My tokens and keys", 'action: "sign-out"'):
        assert x in me, x
    assert '"Help for this page (F1)", action: "help"' in MENU and '"Documentation: every document", href: "#/documentation"' in MENU
    assert '{ label: "Sites", href: "#/farm", dynamic: "farm-sites" }' in MENU   # Local is the first site (R2.1, D646)


def test_wizards_parent_opens_the_wizards_page_and_repository_holds_the_content_framework():
    """Owner, 21:41: "clicking on wizards should take us to base wizard page like before"; "Arch repo and content
    framework need to be together in one menu", "top level and in project both"."""
    for h in ("#/model-admin", "#/project-admin", "#/admin/wizards"):
        assert f'{{ label: "Wizards", href: "{h}", items:' in MENU, h
    repo = MENU[MENU.index('key: "repository"'):MENU.index('key: "help"')]
    assert '{ label: "Architecture Repository", href: "#/repository"' in repo and '{ label: "Content framework", href: "#/metamodel"' in repo
    assert '["architecture", "Architecture", "◫", ["archrepo", "content",' in _src("Projects.jsx")


def test_every_address_the_screens_use_is_in_the_menu():
    used = set()
    for f in list(WEB.glob("*.jsx")) + list(WEB.glob("*.js")):
        for m in re.findall(r'["`](#/[a-z][a-z0-9-]*(?:/[a-z][a-z0-9-]*)?)', f.read_text(encoding="utf-8")):
            used.add(m)
    missing = []
    for u in sorted(used):
        if u in PATHS or u in FROM_A_PAGE or any(u.startswith(k + "/") for k in FROM_A_PAGE):
            continue
        # a one-segment address is reached when the menu has it or a deeper address under it
        if any(p == u or p.startswith(u + "/") for p in PATHS):
            continue
        missing.append(u)
    assert not missing, f"not in the menu (menu.js) nor listed as opened from a page: {missing}"


def test_every_system_admin_tab_is_in_the_menu():
    tabs = re.findall(r'^\s*\["([a-z-]+)", "[^"]+", \(\) =>', _src("Admin.jsx"), re.M)
    assert len(tabs) >= 19
    missing = [t for t in tabs if f"#/admin/{t}" not in PATHS]
    assert not missing, missing


def test_every_project_admin_tab_is_in_the_menu():
    tabs = set(re.findall(r'href="(#/project-admin/[a-z-]+)" className=\{`tab', _src("Projects.jsx")))
    assert len(tabs) >= 7
    assert not (tabs - PATHS), tabs - PATHS


def test_every_repository_part_is_in_the_menu():
    links = set(re.findall(r'label: "[^"]+", href: "(#/[^"]+)"', _src("ArchitectureRepository.jsx")))
    assert len(links) >= 15
    assert not (links - HREFS), links - HREFS


# every address the Classic screens had (the row of areas, the row of menus, quick jump), kept as they were when the
# Classic screens were removed (owner, 12 Nov 2026, R2.25, D606), so none is lost from the menu bar
CLASSIC = {"#/", "#/admin", "#/change-log", "#/compare", "#/compare/common", "#/compare/gaps", "#/enterprise-library",
           "#/library", "#/mcp", "#/merge-requests", "#/metamodel", "#/model-admin", "#/more", "#/my-profile",
           "#/project-admin", "#/reference-library", "#/repository", "#/surveys", "#/work"}


def test_every_classic_menu_and_area_is_in_the_menu():
    classic = CLASSIC | set(re.findall(r'href: "(#/[^"]*)"', _src("Areas.jsx")))
    classic |= set(re.findall(r'\["[^"]+", "(#/[^"]*)"', _src("QuickJump.jsx")))
    # an area's own address lands on its first tab (Wizards), which the menu has as #/<area>/wizards
    missing = [h for h in sorted(classic) if h not in HREFS and h.split("?")[0] not in PATHS and h not in FROM_A_PAGE
               and f"{h}/wizards" not in PATHS]
    assert not missing, missing


def test_every_notification_tab_is_in_the_menu():
    tabs = re.findall(r'\["(inbox|tasks|received|sent|new)"', _src("Notifications.jsx"))
    for t in tabs:
        assert ("#/notifications" if t == "inbox" else f"#/notifications/{t}") in PATHS, t


def test_wizards_have_sub_menus_from_the_same_lists():
    """Owner, 20:55: "Project admin and Model admins should have sub menus for wizards". The menu builds them from the
    lists the pages use (wizardLists.js), so a wizard added to a page is in the menu too; each page opens ?wizard=<k>."""
    lists = _src("wizardLists.js")
    for name in ("MODEL_WIZARDS", "PROJECT_WIZARDS", "SYSTEM_WIZARDS"):
        assert f"export const {name}" in lists and f"{name}.map(" in MENU, name
    assert "#/model-admin/wizards?wizard=${c.k}" in MENU and "#/project-admin?wizard=${w.k}" in MENU
    assert "#/admin/wizards?wizard=${w.k}" in MENU
    assert "MODEL_WIZARDS.flatMap" in _src("ModelAdmin.jsx") and "wizardAsked()" in _src("ModelAdmin.jsx")
    assert "PROJECT_WIZARDS.find((w) => w.k === wizardAsked())" in _src("Projects.jsx")
    assert "SYSTEM_WIZARDS.some((w) => w.k === wizardAsked())" in _src("SystemWizards.jsx")
    keys = re.findall(r'\{ k: "([a-z-]+)"', lists)
    assert len(keys) >= 40


def test_hidden_when_not_allowed_and_no_classic_button():
    """Items a person may not use are hidden (D588); "/" finds (D590). The Classic button is gone (owner, 12 Nov 2026:
    "Remove classic UI button", D603), then the Classic screens (owner: "We can remove them and do a full test", R2.25,
    D606): the menu bar is the only menu; no style switch anywhere (the top bar, My profile, page tabs)."""
    assert "if (it.ok && !it.ok()) continue;" in MENU and "if (it.part && !partOn(it.part)) continue;" in MENU
    app = _src("App.jsx")
    assert "<TopMenu route={route} />" in app and 'className="subnav"' not in app and "<AreaMenu" not in app
    assert "useMenuStyle" not in app and "classic ?" not in app and "!classic" not in app
    for f in ("menu.js", "TopMenu.jsx", "PageNav.jsx", "navActions.js", "QuickJump.jsx", "Skills.jsx", "Areas.jsx"):
        src = _src(f)
        for gone in ("MenuStyleSwitch", "NavStylePicker", "readMenuStyle", "saveMenuStyle", "AreaMenu", "nav-classic", '"classic"'):
            assert gone not in src, (f, gone)
    assert "NavWelcome" not in app and "NavWelcome" not in _src("PageNav.jsx")
    assert 'style === "menu"' not in _src("PageNav.jsx")
    qj = _src("QuickJump.jsx")
    assert 'e.key === "/"' in qj and "menuEntries()" in qj and "/api/v1/search?q=" in qj and "Search everything for" in qj
    assert "<TopSearch find />" in app and "if (find) {" in _src("GridPages.jsx")


def test_model_and_project_library_for_everyone():
    """Owner, 12 Nov 2026: "Model library and Project library should be available to all users. So if a user is not an
    admin ensure menu is adjusted accordingly": both are in Architecture Work, which has no admin check, and the
    Project library has a page of its own (not inside Project Admin); library projects are read by anyone with a role."""
    work = MENU[MENU.index('key: "work"'):MENU.index('key: "model"')]
    assert 'ok:' not in work.split("items:")[0]
    assert '{ label: "Model library", href: "#/library" }' in work
    assert '{ label: "Project library", href: "#/project-library", part: "projects" }' in work
    assert 'route.startsWith("#/project-library") ? <ProjectLibraryPage />' in _src("App.jsx")
    assert "export function ProjectLibraryPage()" in _src("Projects.jsx")
    src = (Path(__file__).resolve().parents[1] / "eax" / "projects.py").read_text(encoding="utf-8")
    assert 'if p.get("is_library") and what == "read" and not roles and (user.roles or ()):' in src
    assert 'r["my_roles"] or (r["is_library"] and (user.roles or ()))' in src
