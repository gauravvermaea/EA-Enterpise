-- =====================================================================================
-- EA Explorer 0.3.1: rules about relationships (D113)
-- Run by Alembic (migrations/versions/0007_relationship_rules.py). Checked by tests/sql/phase3_1_checks.sql.
--
-- A rule can now say an entity must have a relationship: rule type has_relationship, on the built-in
-- field "relationships". param1 is the relationship type (its name or code; empty: any), param2 the
-- entity type at the other end (name or code; empty: any). Either direction counts. Like every rule
-- it warns and never blocks (D48). The entity page's Rules tab lists every rule passed and failed.
-- =====================================================================================

-- still version 0.3.1 (one row per version): note the addition on its row
UPDATE core.schema_versions SET description = description || '; rules that an entity has a relationship (0007)'
 WHERE version = '0.3.1';

INSERT INTO core.rule_types (code, name, description) VALUES
    ('has_relationship', 'Has relationship',
     'At least one relationship of the type in param1 (empty: any) to or from an entity of the type in param2 (empty: any)');

ALTER TABLE core.validation_rules DROP CONSTRAINT IF EXISTS validation_rules_field_name_check;
ALTER TABLE core.validation_rules
    ADD CONSTRAINT validation_rules_field_name_check
        CHECK (field_name IN ('name', 'description', 'display_id', 'relationships')),
    ADD CONSTRAINT validation_rules_relationship_rule
        CHECK ((rule_type_code = 'has_relationship') = (coalesce(field_name, '') = 'relationships'));
