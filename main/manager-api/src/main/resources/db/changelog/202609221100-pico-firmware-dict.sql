-- Pico 品牌收尾：清理固件类型字典里残留的小智字样。
-- 该字典驱动"手动添加设备"和"设备管理"页的板型下拉，显示名应与固件 Kconfig 保持一致。
UPDATE `sys_dict_data`
SET `dict_label` = 'Movecall Moji'
WHERE `dict_value` = 'movecall-moji-esp32s3'
  AND `dict_label` LIKE '%小智%';

UPDATE `sys_dict_data`
SET `remark` = 'Movecall Moji'
WHERE `dict_value` = 'movecall-moji-esp32s3'
  AND `remark` LIKE '%小智%';
