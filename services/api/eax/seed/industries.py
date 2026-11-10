"""The industry reference models (phase 39, D470-D472): one locked reference model per industry, beside the
insurance reference model, built from the owner's industry starter packs by tools/build_industry_models.py.
Each appears in the library (Enterprise reference library) and can be the base of a new model.

The seed (eax.seed.__main__) loads any that are missing, on a fresh install and on an upgrade alike: no migration.
"""

from . import industry_healthcare, industry_manufacturing, industry_pharmaceuticals, industry_retail

_SCOPE = ("capabilities to level 3, value streams, business services, processes and functions, products, business "
          "objects, a starter application landscape with its application services, technology services, actors and "
          "roles, on ArchiMate 4. Read-only: copy it to start a model.")

# (code, industry name, version, description, content module)
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
]


def key(code: str) -> str:
    """The model key (the guid is made from it); the version is in the key, so a new version is a new model."""
    version = next(v for c, _n, v, *_ in MODELS if c == code)
    return f"{code}-reference-{version}"
