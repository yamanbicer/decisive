// Browser Supabase client (Auth). Returns null until NEXT_PUBLIC_SUPABASE_* are set,
// so the app runs against the dev/in-memory backend before auth lands.
import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
const anon = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

export const supabase: SupabaseClient | null =
  url && anon ? createClient(url, anon) : null;
