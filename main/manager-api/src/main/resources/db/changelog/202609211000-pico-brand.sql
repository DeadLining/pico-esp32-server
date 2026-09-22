-- Additive Pico migration: never edit checksummed upstream migrations.
UPDATE sys_params SET param_value = 'pico-server'
 WHERE param_code = 'server.name' AND param_value = 'xiaozhi-esp32-server';
UPDATE sys_params SET param_value = REPLACE(param_value, '小智', 'Pico')
 WHERE param_code = 'system_error_response';
UPDATE ai_agent_template SET agent_code = 'Pico' WHERE agent_code = '小智';
UPDATE ai_agent_template SET agent_name = 'Pico' WHERE agent_name = '小智';
-- This is a configuration-section identifier, not a board type.
UPDATE sys_params SET param_code = 'pico', remark = 'Pico 类型' WHERE param_code = 'xiaozhi';
