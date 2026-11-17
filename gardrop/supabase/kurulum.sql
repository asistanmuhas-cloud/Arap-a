-- Gardrop bulut senkronu. Supabase > SQL Editor'de bir kez çalıştır.
-- Her kullanıcı yalnız kendi satırlarını ve fotoğraflarını görür (RLS).

create table if not exists public.kayitlar (
  kullanici uuid not null default auth.uid() references auth.users (id) on delete cascade,
  depo text not null,
  id text not null,
  guncelleme timestamptz,
  degisim timestamptz not null default now(),  -- sunucu saati; istemci bu imleçle çeker
  veri jsonb not null,
  primary key (kullanici, depo, id)
);
create index if not exists kayitlar_degisim on public.kayitlar (kullanici, degisim);

-- Her yazımda degisim'i sunucu saatine çek; daha eski bir kayıt yenisinin üstüne yazılmasın.
create or replace function public.kayitlar_yaz() returns trigger language plpgsql as $$
begin
  if tg_op = 'UPDATE' and old.guncelleme is not null and new.guncelleme is not null and new.guncelleme < old.guncelleme then
    return old;  -- eski sürüm: yok say
  end if;
  new.degisim := clock_timestamp();
  return new;
end $$;
drop trigger if exists kayitlar_yaz on public.kayitlar;
create trigger kayitlar_yaz before insert or update on public.kayitlar for each row execute function public.kayitlar_yaz();

alter table public.kayitlar enable row level security;
drop policy if exists "kendi kayitlari" on public.kayitlar;
create policy "kendi kayitlari" on public.kayitlar for all to authenticated
  using (kullanici = auth.uid()) with check (kullanici = auth.uid());

-- Fotoğraflar: özel "gorseller" kovası, yol: <kullanici-id>/<gorsel-id>
insert into storage.buckets (id, name, public) values ('gorseller', 'gorseller', false) on conflict (id) do nothing;
drop policy if exists "kendi gorselleri okur" on storage.objects;
drop policy if exists "kendi gorsellerini yazar" on storage.objects;
drop policy if exists "kendi gorsellerini gunceller" on storage.objects;
drop policy if exists "kendi gorsellerini siler" on storage.objects;
create policy "kendi gorselleri okur" on storage.objects for select to authenticated
  using (bucket_id = 'gorseller' and (storage.foldername(name))[1] = auth.uid()::text);
create policy "kendi gorsellerini yazar" on storage.objects for insert to authenticated
  with check (bucket_id = 'gorseller' and (storage.foldername(name))[1] = auth.uid()::text);
create policy "kendi gorsellerini gunceller" on storage.objects for update to authenticated
  using (bucket_id = 'gorseller' and (storage.foldername(name))[1] = auth.uid()::text);
create policy "kendi gorsellerini siler" on storage.objects for delete to authenticated
  using (bucket_id = 'gorseller' and (storage.foldername(name))[1] = auth.uid()::text);
