-- 0002_view_links: "viewpoint" became "view" in EA Explorer (owner, 9 Nov 2026, D399). Links into EA Explorer written
-- ea:viewpoint:<model>:<code> are now ea:view:<model>:<code>, in links, in pages and in the history kept for undo.
UPDATE lib.entries SET href = 'ea:view:' || substr(href, length('ea:viewpoint:') + 1) WHERE href LIKE 'ea:viewpoint:%';
UPDATE lib.entries SET blocks = replace(blocks::text, 'ea:viewpoint:', 'ea:view:')::jsonb,
                       search_doc = replace(search_doc, 'ea:viewpoint:', 'ea:view:')
 WHERE blocks::text LIKE '%ea:viewpoint:%' OR search_doc LIKE '%ea:viewpoint:%';
UPDATE lib.changes SET before = replace(before::text, 'ea:viewpoint:', 'ea:view:')::jsonb WHERE before::text LIKE '%ea:viewpoint:%';
UPDATE lib.changes SET after = replace(after::text, 'ea:viewpoint:', 'ea:view:')::jsonb WHERE after::text LIKE '%ea:viewpoint:%';
