-- Additive Pico migration: never edit checksummed upstream migrations.
-- The upstream default was a vendor placeholder (http://xiaozhi.server.com) that
-- is not reachable. Devices display this URL together with the 6-digit activation
-- code, so it must point at the real Pico console entry.
UPDATE sys_params SET param_value = 'https://82.157.168.149'
 WHERE param_code = 'server.fronted_url'
   AND param_value = 'http://xiaozhi.server.com';
