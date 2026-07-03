"use strict";

const { json } = require("./_account");

exports.handler = async () => {
  const supabaseUrl = process.env.SUPABASE_URL || null;
  const supabaseAnonKey = process.env.SUPABASE_ANON_KEY || null;
  return json(200, {
    supabase_url: supabaseUrl,
    supabase_anon_key: supabaseAnonKey,
    auth_enabled: Boolean(supabaseUrl && supabaseAnonKey),
  });
};
