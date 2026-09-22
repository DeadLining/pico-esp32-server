package pico.modules.security;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import org.junit.jupiter.api.Test;
import org.springframework.core.env.Environment;
import org.springframework.jdbc.core.JdbcTemplate;
import pico.modules.sys.service.SysUserService;

class AdminBootstrapTest {
    final JdbcTemplate jdbc=mock(JdbcTemplate.class);
    final SysUserService users=mock(SysUserService.class);
    final Environment env=mock(Environment.class);
    final AdminBootstrap bootstrap=new AdminBootstrap(jdbc,users,env);
    @Test void existingAdminIsNeverChanged() {
        when(jdbc.queryForObject("SELECT COUNT(*) FROM sys_user WHERE super_admin=1 AND status=1",Long.class)).thenReturn(1L);
        bootstrap.run(null); verifyNoInteractions(users,env);
    }
    @Test void noCredentialMeansNoDefaultPassword() {
        when(jdbc.queryForObject("SELECT COUNT(*) FROM sys_user",Long.class)).thenReturn(0L);
        assertThrows(IllegalStateException.class,()->bootstrap.run(null)); verifyNoInteractions(users);
    }
    @Test void ordinaryAccountsAreNeverPromotedAutomatically() {
        when(jdbc.queryForObject("SELECT COUNT(*) FROM sys_user",Long.class)).thenReturn(1L);
        assertThrows(IllegalStateException.class,()->bootstrap.run(null)); verifyNoInteractions(users,env);
    }
    @Test void emptyDatabaseUsesEnvironmentSecretViaExistingHashingService() {
        when(jdbc.queryForObject("SELECT COUNT(*) FROM sys_user",Long.class)).thenReturn(0L);
        when(env.getProperty("PICO_ADMIN_USERNAME")).thenReturn("pico");
        when(env.getProperty("PICO_ADMIN_PASSWORD")).thenReturn("test-fixture-Only-Strong-123!");
        bootstrap.run(null); verify(users).save(argThat(u->u.getUsername().equals("pico") && u.getPassword().equals("test-fixture-Only-Strong-123!")));
    }
}
