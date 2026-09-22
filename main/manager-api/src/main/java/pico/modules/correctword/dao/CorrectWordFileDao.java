package pico.modules.correctword.dao;

import org.apache.ibatis.annotations.Mapper;

import pico.common.dao.BaseDao;
import pico.modules.correctword.entity.CorrectWordFileEntity;

@Mapper
public interface CorrectWordFileDao extends BaseDao<CorrectWordFileEntity> {
}
