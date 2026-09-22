package pico.modules.security;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.AfterEach;
import org.mockito.MockedStatic;
import pico.common.utils.MessageUtils;
import pico.common.exception.RenException;
import pico.common.utils.Sm2DecryptUtil;
import pico.modules.security.controller.LoginController;
import pico.modules.security.dto.LoginDTO;
import pico.modules.security.password.PasswordUtils;
import pico.modules.security.service.*;
import pico.modules.sys.dto.SysUserDTO;
import pico.modules.sys.service.*;

class AdminOnlyLoginTest {
    MockedStatic<MessageUtils> messages;
    @BeforeEach void stubMessages() { messages=mockStatic(MessageUtils.class); }
    @AfterEach void closeMessages() { messages.close(); }
    final SysUserService users=mock(SysUserService.class);
    final SysUserTokenService tokens=mock(SysUserTokenService.class);
    final CaptchaService captcha=mock(CaptchaService.class);
    final SysParamsService params=mock(SysParamsService.class);
    final LoginController controller=new LoginController(users,tokens,captcha,params,mock(SysDictDataService.class));

    @Test void registrationCannotBeEnabledByDatabaseSetting() {
        when(users.getAllowUserRegister()).thenReturn(true);
        assertThrows(RenException.class,()->controller.register(new LoginDTO()));
        verifyNoInteractions(captcha,params); verify(users,never()).save(any());
    }
    @Test void publicSmsAndRecoveryAreDisabledBeforeAnySideEffect() {
        assertThrows(RenException.class,()->controller.smsVerification(null));
        assertThrows(RenException.class,()->controller.retrievePassword(null));
        verifyNoInteractions(captcha,params,users,tokens);
    }
    @Test void normalAccountCannotReceiveToken() { checkLogin(0,1,false); }
    @Test void disabledAdminCannotReceiveToken() { checkLogin(1,0,false); }
    @Test void missingAdminFlagCannotReceiveToken() { checkLogin(null,1,false); }
    @Test void activeAdminCanReceiveToken() { checkLogin(1,1,true); }
    void checkLogin(Integer admin,Integer status,boolean allowed) {
        var user=new SysUserDTO();user.setId(7L);user.setSuperAdmin(admin);user.setStatus(status);user.setPassword("hash");
        when(users.getByUsername("pico")).thenReturn(user);
        var dto=new LoginDTO();dto.setUsername("pico");dto.setPassword("cipher");dto.setCaptchaId("challenge");
        try(var decrypt=mockStatic(Sm2DecryptUtil.class);var password=mockStatic(PasswordUtils.class)) {
            decrypt.when(()->Sm2DecryptUtil.decryptAndValidateCaptcha("cipher","challenge",captcha,params)).thenReturn("password");
            password.when(()->PasswordUtils.matches("password","hash")).thenReturn(true);
            if(allowed) {controller.login(dto);verify(tokens).createToken(7L);}
            else {assertThrows(RenException.class,()->controller.login(dto));verifyNoInteractions(tokens);}
        }
    }
}
