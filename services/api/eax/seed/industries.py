"""The industry reference models (phase 39, D470-D472): one locked reference model per industry, beside the
insurance reference model, built from the owner's industry starter packs by tools/build_industry_models.py.
Each appears in the library (Enterprise reference library) and can be the base of a new model.

The seed (eax.seed.__main__) loads any that are missing, on a fresh install and on an upgrade alike: no migration.
"""

from . import (
    industry_banking,
    industry_government,
    industry_healthcare,
    industry_logistics,
    industry_manufacturing,
    industry_meridian,
    industry_minerals_mining,
    industry_pharmaceuticals,
    industry_retail,
    industry_telecommunications,
)

_SCOPE = ("capabilities to level 3, value streams, business services, processes and functions, products, business "
          "objects, a starter application landscape with its application services, technology services, actors and "
          "roles, on ArchiMate 4. Read-only: copy it to start a model.")

# (code, industry name, version, description, content module[, model name]); the model is called
# "<industry> reference model" unless a name is given (the insurance worked example, D549)
MODELS = [
    ("healthcare", "Healthcare", "1.0",
     "Industry reference model for a provider healthcare network (patients, encounters, clinical pathways and the "
     "records that follow them): " + _SCOPE, industry_healthcare),
    ("manufacturing", "Manufacturing", "1.0",
     "Industry reference model for a discrete and process manufacturer (product development, planning, plant "
     "operations, quality and maintenance): " + _SCOPE, industry_manufacturing),
    ("pharmaceuticals", "Pharmaceuticals", "1.0",
     "Industry reference model for a pharmaceutical company (discovery, clinical development, regulatory, GMP "
     "manufacturing, safety and commercial): " + _SCOPE, industry_pharmaceuticals),
    ("retail", "Retail", "1.0",
     "Industry reference model for a multi-channel retailer (ranging, sourcing, stores, e-commerce, fulfilment "
     "and loyalty): " + _SCOPE, industry_retail),
    # owner, 10 Nov 2026 (D548, D549): Banking from its pack, four more industries from the owner's metamodels by
    # industry, and the insurance worked example (Meridian Assurance Group) as a model of its own beside the unchanged
    # Insurance reference model
    ("banking", "Banking", "1.0",
     "Industry reference model for a retail and commercial bank (deposits, lending, cards, payments, treasury, "
     "financial crime and regulatory reporting): " + _SCOPE, industry_banking),
    ("government", "Government", "1.0",
     "Industry reference model for a provincial or local government administration (citizen services, benefits, "
     "revenue, registers, grants, procurement and inspections): " + _SCOPE, industry_government),
    ("logistics", "Logistics", "1.0",
     "Industry reference model for a freight and logistics company (booking, rating, transport, warehousing, customs, "
     "track and trace, billing): " + _SCOPE, industry_logistics),
    ("minerals_mining", "Minerals and Mining", "1.0",
     "Industry reference model for a mining company (geology, mine planning, extraction, processing, metal accounting, "
     "safety, tailings and logistics): " + _SCOPE, industry_minerals_mining),
    ("telecommunications", "Telecommunications", "1.0",
     "Industry reference model for a telecommunications operator (products, ordering, provisioning, billing, network "
     "assurance, field service and interconnect): " + _SCOPE, industry_telecommunications),
    ("meridian", "Insurance", "1.0",
     "The insurance worked example: Meridian Assurance Group, an invented South African life and short-term insurer, "
     "from the owner's populated TOGAF content metamodel workbook: capabilities to level 4, value streams, business "
     "services, processes, functions, products, data entities, its application landscape and their services, "
     "technology services, actors and roles, on ArchiMate 4. Read-only: copy it to start a model.", industry_meridian,
     "Meridian Assurance (insurance worked example)"),
]


def model_name(code: str) -> str:
    """The model's name: "<industry> reference model", or the name given."""
    row = next(m for m in MODELS if m[0] == code)
    return row[5] if len(row) > 5 else f"{row[1]} reference model"


def key(code: str) -> str:
    """The model key (the guid is made from it); the version is in the key, so a new version is a new model."""
    version = next(v for c, _n, v, *_ in MODELS if c == code)
    return f"{code}-reference-{version}"
