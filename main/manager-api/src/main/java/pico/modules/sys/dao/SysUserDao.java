package pico.modules.sys.dao;

import org.apache.ibatis.annotations.Mapper;

import pico.common.dao.BaseDao;
import pico.modules.sys.entity.SysUserEntity;

/**
 * 系统用户
 */
@Mapper
public interface SysUserDao extends BaseDao<SysUserEntity> {

}