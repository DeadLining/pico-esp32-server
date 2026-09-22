package pico.modules.agent.service;

import pico.modules.agent.entity.AgentChatTitleEntity;

public interface AgentChatTitleService {

    void saveOrUpdateTitle(String sessionId, String title);

    String getTitleBySessionId(String sessionId);
}