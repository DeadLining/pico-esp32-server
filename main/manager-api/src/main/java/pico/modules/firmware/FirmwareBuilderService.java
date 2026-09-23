package pico.modules.firmware;

import java.io.IOException;
import java.util.List;
import java.util.Map;
import java.util.NoSuchElementException;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

/**
 * Thin HTTP client for the internal firmware-builder service.
 *
 * The builder owns compilation, artifact storage and the build cache; this class
 * only proxies requests to it. It deliberately keeps no local build state: an
 * earlier local-compilation path is gone, so there is exactly one place that
 * turns source into firmware.
 */
@Service
public class FirmwareBuilderService {
    private final ObjectMapper json = new ObjectMapper();

    @Value("${PICO_FIRMWARE_BUILDER_URL:http://firmware-builder:8090}")
    private String builderUrl;

    public Map<String,Object> health() {
        try {
            var c = (java.net.HttpURLConnection) java.net.URI.create(builderUrl + "/health").toURL().openConnection();
            c.setConnectTimeout(2000); c.setReadTimeout(3000);
            int code = c.getResponseCode();
            if (code != 200) return Map.of("status", "not_ready", "error", "builder returned " + code);
            return json.readValue(c.getInputStream(), new TypeReference<Map<String,Object>>(){});
        } catch (Exception e) {
            return Map.of("status", "not_ready", "error", e.getMessage() == null ? "builder unavailable" : e.getMessage());
        }
    }

    public Map<String,Object> boards() {
        try {
            return json.readValue(java.net.URI.create(builderUrl+"/boards").toURL().openStream(), new TypeReference<Map<String,Object>>(){});
        } catch(Exception e) {
            return Map.of("boards", List.of(), "languages", List.of(), "error", e.getMessage());
        }
    }

    public Map<String,Object> create(FirmwareBuilderController.BuildRequest r) {
        if(!r.getBoard().matches("[a-z0-9][a-z0-9._/-]*")||r.getBoard().contains("..")||!r.getName().matches("[a-z0-9][a-z0-9.-]*")) throw new IllegalArgumentException("invalid board");
        try {
            var c=(java.net.HttpURLConnection)java.net.URI.create(builderUrl+"/build").toURL().openConnection();
            c.setRequestMethod("POST");
            c.setDoOutput(true);
            c.setRequestProperty("Content-Type","application/json");
            c.getOutputStream().write(json.writeValueAsBytes(Map.of(
                "board",r.getBoard(),"name",r.getName(),"target",r.getTarget(),
                "language",r.getLanguage(),"wake_word",r.getWakeWord(),
                "build_options",r.getBuildOptions()==null?Map.of():r.getBuildOptions())));
            return json.readValue(c.getInputStream(),new TypeReference<Map<String,Object>>(){});
        } catch(Exception e) {
            throw new IllegalStateException("firmware builder unavailable",e);
        }
    }

    public Map<String,Object> builds() {
        try {
            return json.readValue(java.net.URI.create(builderUrl+"/builds").toURL().openStream(), new TypeReference<Map<String,Object>>(){});
        } catch(Exception e) {
            return Map.of("builds", List.of(), "error", e.getMessage());
        }
    }

    public Map<String,Object> status(String id) {
        try {
            return json.readValue(java.net.URI.create(builderUrl+"/build/"+id).toURL().openStream(),new TypeReference<Map<String,Object>>(){});
        } catch(Exception e) {
            throw new NoSuchElementException("build not found");
        }
    }

    public Map<String,Object> delete(String id) {
        if(id==null||!id.matches("[a-f0-9-]+")) throw new NoSuchElementException("build not found");
        try {
            var c=(java.net.HttpURLConnection)java.net.URI.create(builderUrl+"/build/"+id).toURL().openConnection();
            c.setRequestMethod("DELETE");
            int code=c.getResponseCode();
            if(code==404) throw new NoSuchElementException("build not found");
            if(code==409) {
                // A build with a live compile process must not be wiped out mid-write.
                var busy=new pico.common.exception.RenException("正在编译，任务结束后才能清理");
                busy.setCode(409);
                throw busy;
            }
            if(code!=200) throw new IllegalStateException("firmware builder unavailable");
            return json.readValue(c.getInputStream(),new TypeReference<Map<String,Object>>(){});
        } catch(NoSuchElementException e) { throw e; }
        catch(pico.common.exception.RenException e) { throw e; }
        catch(Exception e) { throw new IllegalStateException("firmware builder unavailable",e); }
    }

    public byte[] builderFile(String id,String name) throws IOException {
        if(!name.matches("[A-Za-z0-9_.-]+")||name.contains("..")) throw new IOException("invalid artifact");
        var c=(java.net.HttpURLConnection)java.net.URI.create(builderUrl+"/build/"+id+"/artifact/"+name).toURL().openConnection();
        if(c.getResponseCode()!=200) throw new IOException("artifact unavailable");
        return c.getInputStream().readAllBytes();
    }

    public byte[] builderManifest(String id) throws IOException {
        var c=(java.net.HttpURLConnection)java.net.URI.create(builderUrl+"/build/"+id+"/manifest").toURL().openConnection();
        if(c.getResponseCode()!=200) throw new IOException("manifest unavailable");
        return c.getInputStream().readAllBytes();
    }
}
