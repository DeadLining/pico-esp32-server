package pico.modules.security;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import pico.modules.sys.dto.SysUserDTO;
import pico.modules.sys.service.SysUserService;

/** Local, environment-only first-admin provisioning. Never reset an existing password. */
@Component
public class AdminBootstrap implements ApplicationRunner {
    private final JdbcTemplate jdbc;
    private final SysUserService users;
    private final Environment env;

    public AdminBootstrap(JdbcTemplate jdbc, SysUserService users, Environment env) {
        this.jdbc=jdbc; this.users=users; this.env=env;
    }

    @Override
    public void run(ApplicationArguments args) {
        Long admins=jdbc.queryForObject("SELECT COUNT(*) FROM sys_user WHERE super_admin=1 AND status=1", Long.class);
        if (admins != null && admins > 0) return;
        Long count=jdbc.queryForObject("SELECT COUNT(*) FROM sys_user", Long.class);
        if (count == null || count != 0) {
            throw new IllegalStateException("No active Pico administrator; restore an administrator locally before starting");
        }
        String username=env.getProperty("PICO_ADMIN_USERNAME");
        String password=env.getProperty("PICO_ADMIN_PASSWORD");
        if (username == null || !username.matches("[a-zA-Z0-9_-]{3,32}") || password == null || password.length() < 16) {
            throw new IllegalStateException("Empty database: set PICO_ADMIN_USERNAME and a strong PICO_ADMIN_PASSWORD locally");
        }
        SysUserDTO user=new SysUserDTO();
        user.setUsername(username); user.setPassword(password); user.setRealName("Pico 管理员");
        // The existing service hashes the password and makes the first account super-admin.
        users.save(user);
    }
}
