package pico.modules.agent.dao;

import org.apache.ibatis.annotations.Mapper;
import pico.common.dao.BaseDao;
import pico.modules.agent.entity.AgentContextProviderEntity;

@Mapper
public interface AgentContextProviderDao extends BaseDao<AgentContextProviderEntity> {
}
