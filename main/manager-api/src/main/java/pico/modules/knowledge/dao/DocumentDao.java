package pico.modules.knowledge.dao;

import org.apache.ibatis.annotations.Mapper;
import pico.common.dao.BaseDao;
import pico.modules.knowledge.entity.DocumentEntity;

/**
 * 文档 DAO
 */
@Mapper
public interface DocumentDao extends BaseDao<DocumentEntity> {
}
