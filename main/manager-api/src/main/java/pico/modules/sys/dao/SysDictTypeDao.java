package pico.modules.sys.dao;

import org.apache.ibatis.annotations.Mapper;

import pico.common.dao.BaseDao;
import pico.modules.sys.entity.SysDictTypeEntity;

/**
 * 字典类型
 */
@Mapper
public interface SysDictTypeDao extends BaseDao<SysDictTypeEntity> {

}
