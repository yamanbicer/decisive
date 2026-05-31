-- Per-agent skill files + conflict pairing (ROADMAP §7.5 sophistication upgrade).
-- Additive + idempotent. `conflict_partner` is a plain uuid (not a FK) so re-seeding
-- agents never trips a self-referential FK on delete order (cf. owner_id/created_by).
alter table agents add column if not exists skills             jsonb default '[]';
alter table agents add column if not exists conflict_partner   uuid;
alter table agents add column if not exists conflict_dimension text;
