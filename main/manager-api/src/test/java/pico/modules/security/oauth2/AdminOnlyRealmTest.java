package pico.modules.security.oauth2;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import java.util.Date;
import org.junit.jupiter.api.Test;
import org.apache.shiro.authc.DisabledAccountException;
import org.springframework.test.util.ReflectionTestUtils;
import pico.modules.security.entity.SysUserTokenEntity;
import pico.modules.security.service.ShiroService;
import pico.modules.sys.entity.SysUserEntity;

class AdminOnlyRealmTest {
    @Test void oldOrdinaryUserTokenIsRejected() { check(0,false); }
    @Test void adminTokenIsAccepted() { check(1,true); }
    @Test void missingAdminFlagIsRejected() { check(null,false); }
    void check(Integer admin,boolean allowed) {
        var service=mock(ShiroService.class);var realm=new Oauth2Realm();
        ReflectionTestUtils.setField(realm,"shiroService",service);
        var token=new SysUserTokenEntity();token.setUserId(1L);token.setExpireDate(new Date(System.currentTimeMillis()+60000));
        when(service.getByToken("test-token")).thenReturn(token);
        var user=new SysUserEntity();user.setId(1L);user.setStatus(1);user.setSuperAdmin(admin);
        when(service.getUser(1L)).thenReturn(user);
        if(allowed) assertNotNull(realm.doGetAuthenticationInfo(new Oauth2Token("test-token")));
        else assertThrows(DisabledAccountException.class,()->realm.doGetAuthenticationInfo(new Oauth2Token("test-token")));
    }
}
