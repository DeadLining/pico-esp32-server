package pico.modules.sys.service.impl;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotSame;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;

import pico.common.redis.RedisKeys;
import pico.common.redis.RedisUtils;
import pico.modules.sys.dao.SysUserDao;
import pico.modules.sys.vo.SysDictDataItem;

class SysDictDataServiceImplTest {

    @Test
    void cachedDictionaryItemsAreCheckedAndReturnedAsDtos() {
        RedisUtils redisUtils = mock(RedisUtils.class);
        SysDictDataItem item = new SysDictDataItem();
        item.setName("enabled");
        item.setKey("1");
        List<SysDictDataItem> cached = new ArrayList<>(List.of(item));
        when(redisUtils.get(RedisKeys.getDictDataByTypeKey("status"))).thenReturn(cached);
        SysDictDataServiceImpl service = new SysDictDataServiceImpl(mock(SysUserDao.class), redisUtils);

        List<SysDictDataItem> result = service.getDictDataByType("status");

        assertNotSame(cached, result);
        assertEquals(List.of(item), result);
    }
}
