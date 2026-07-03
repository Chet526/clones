-- GeoBrief SaaS account model (Supabase-hosted auth + Stripe metadata mirror)

create extension if not exists pgcrypto;

create table if not exists public.account_profiles (
	user_id uuid primary key references auth.users (id) on delete cascade,
	email text not null unique,
	full_name text,
	marketing_opt_in boolean not null default false,
	stripe_customer_id text unique,
	plan text not null default 'standard' check (plan in ('standard', 'pro')),
	subscription_status text,
	current_period_end timestamptz,
	created_at timestamptz not null default now(),
	updated_at timestamptz not null default now()
);

create table if not exists public.email_sequences (
	id bigserial primary key,
	slug text not null unique,
	name text not null,
	description text,
	created_at timestamptz not null default now()
);

create table if not exists public.email_sequence_steps (
	id bigserial primary key,
	sequence_id bigint not null references public.email_sequences (id) on delete cascade,
	step_order int not null,
	delay_hours int not null default 0,
	subject text not null,
	body_template text not null,
	created_at timestamptz not null default now(),
	unique (sequence_id, step_order)
);

create table if not exists public.email_dispatch_log (
	id bigserial primary key,
	user_id uuid references auth.users (id) on delete cascade,
	sequence_slug text not null,
	step_order int not null,
	recipient text not null,
	status text not null,
	provider_message_id text,
	sent_at timestamptz not null default now()
);

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
	new.updated_at := now();
	return new;
end;
$$;

drop trigger if exists trg_account_profiles_updated_at on public.account_profiles;
create trigger trg_account_profiles_updated_at
before update on public.account_profiles
for each row execute function public.set_updated_at();

create or replace function public.handle_new_auth_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
	insert into public.account_profiles (user_id, email, full_name)
	values (
		new.id,
		coalesce(new.email, ''),
		coalesce(new.raw_user_meta_data ->> 'full_name', null)
	)
	on conflict (user_id) do update
		set email = excluded.email,
			full_name = coalesce(excluded.full_name, public.account_profiles.full_name);
	return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
after insert on auth.users
for each row execute procedure public.handle_new_auth_user();

alter table public.account_profiles enable row level security;

drop policy if exists "Users can view own profile" on public.account_profiles;
create policy "Users can view own profile"
on public.account_profiles
for select
to authenticated
using (auth.uid() = user_id);

drop policy if exists "Users can update own profile" on public.account_profiles;
create policy "Users can update own profile"
on public.account_profiles
for update
to authenticated
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

insert into public.email_sequences (slug, name, description)
values (
	'investigator-onboarding',
	'Investigator Onboarding',
	'Initial SaaS onboarding sequence for new GeoBrief subscribers.'
)
on conflict (slug) do nothing;

with seq as (
	select id from public.email_sequences where slug = 'investigator-onboarding'
)
insert into public.email_sequence_steps (
	sequence_id,
	step_order,
	delay_hours,
	subject,
	body_template
)
select seq.id, steps.step_order, steps.delay_hours, steps.subject, steps.body_template
from seq
cross join (
	values
		(
			1,
			0,
			'Welcome to GeoBrief LE',
			'Your account is ready. Start by logging in at {{account_url}} and connecting your first case file.'
		),
		(
			2,
			24,
			'GeoBrief setup checklist',
			'Configure timezone defaults, upload training data, and verify your chain-of-custody report flow.'
		),
		(
			3,
			72,
			'Pro assistant quick tips',
			'Try prompts for dwell, gaps, and impossible jumps to generate a court-review draft faster.'
		)
) as steps(step_order, delay_hours, subject, body_template)
where not exists (
	select 1
	from public.email_sequence_steps existing
	where existing.sequence_id = seq.id
	  and existing.step_order = steps.step_order
);
