package pico.modules.firmware;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.*;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

@Service
public class FirmwareBuilderService {
    private final ObjectMapper json = new ObjectMapper();
    private final ExecutorService executor = Executors.newFixedThreadPool(1);
    private final Map<String, Job> jobs = new ConcurrentHashMap<>();
    private final Path source;
    private final Path root;
    @Value("${PICO_FIRMWARE_BUILDER_URL:http://firmware-builder:8090}") private String builderUrl;
    public FirmwareBuilderService() { source=Path.of("/tmp"); root=Path.of("/tmp"); }
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
    public Map<String,Object> boards() { try { return json.readValue(java.net.URI.create(builderUrl+"/boards").toURL().openStream(), new TypeReference<Map<String,Object>>(){}); } catch(Exception e) { return Map.of("boards", List.of(), "languages", List.of(), "error", e.getMessage()); } }
    private Object runList(String arg) throws Exception { Process p=new ProcessBuilder("python3", "scripts/build.py", arg, "--json").directory(source.toFile()).redirectErrorStream(true).start(); String out=new String(p.getInputStream().readAllBytes(), StandardCharsets.UTF_8); if(p.waitFor()!=0) throw new IOException(out); return json.readValue(out, Object.class); }
    public Map<String,Object> create(FirmwareBuilderController.BuildRequest r) {
        if(!r.getBoard().matches("[a-z0-9][a-z0-9._/-]*")||r.getBoard().contains("..")||!r.getName().matches("[a-z0-9][a-z0-9.-]*")) throw new IllegalArgumentException("invalid board");
        try { var c=(java.net.HttpURLConnection)java.net.URI.create(builderUrl+"/build").toURL().openConnection(); c.setRequestMethod("POST"); c.setDoOutput(true); c.setRequestProperty("Content-Type","application/json"); c.getOutputStream().write(json.writeValueAsBytes(Map.of("board",r.getBoard(),"name",r.getName(),"target",r.getTarget(),"language",r.getLanguage(),"wake_word",r.getWakeWord(),"build_options",r.getBuildOptions()==null?Map.of():r.getBuildOptions()))); return json.readValue(c.getInputStream(),new TypeReference<Map<String,Object>>(){}); } catch(Exception e) { throw new IllegalStateException("firmware builder unavailable",e); }
    }
    public Map<String,Object> builds() { try { return json.readValue(java.net.URI.create(builderUrl+"/builds").toURL().openStream(), new TypeReference<Map<String,Object>>(){}); } catch(Exception e) { return Map.of("builds", List.of(), "error", e.getMessage()); } }
    public Map<String,Object> status(String id) { try { return json.readValue(java.net.URI.create(builderUrl+"/build/"+id).toURL().openStream(),new TypeReference<Map<String,Object>>(){}); } catch(Exception e) { throw new NoSuchElementException("build not found"); } }
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
    public byte[] builderFile(String id,String name) throws IOException { if(!name.matches("[A-Za-z0-9_.-]+")||name.contains("..")) throw new IOException("invalid artifact"); var c=(java.net.HttpURLConnection)java.net.URI.create(builderUrl+"/build/"+id+"/artifact/"+name).toURL().openConnection(); if(c.getResponseCode()!=200) throw new IOException("artifact unavailable"); return c.getInputStream().readAllBytes(); }
    public byte[] builderManifest(String id) throws IOException { var c=(java.net.HttpURLConnection)java.net.URI.create(builderUrl+"/build/"+id+"/manifest").toURL().openConnection(); if(c.getResponseCode()!=200) throw new IOException("manifest unavailable"); return c.getInputStream().readAllBytes(); }
    private void run(Job j,FirmwareBuilderController.BuildRequest r) { try { j.status="running"; j.progress=5; Files.createDirectories(j.dir); String opts=json.writeValueAsString(r.getBuildOptions()==null?Map.of():r.getBuildOptions()); Process p=new ProcessBuilder("python3","scripts/build.py",r.getBoard(),"--name",r.getName(),"--language",r.getLanguage(),"--wake-word",r.getWakeWord(),"--build-options-json",opts).directory(source.toFile()).redirectErrorStream(true).start(); j.log=new String(p.getInputStream().readAllBytes(),StandardCharsets.UTF_8); int code=p.waitFor(); if(code!=0) throw new IOException("build exited "+code); Path build=source.resolve("build"); Files.copy(build.resolve("merged-binary.bin"),j.dir.resolve("merged-binary.bin")); if(Files.exists(build.resolve("xiaozhi.bin"))) Files.copy(build.resolve("xiaozhi.bin"),j.dir.resolve("xiaozhi.bin")); List<Map<String,Object>> fs=new ArrayList<>(); for(String n:List.of("merged-binary.bin")){Path f=j.dir.resolve(n);if(Files.exists(f))fs.add(Map.of("name",n,"sha256",sha(f),"size",Files.size(f)));} Map<String,Object> m=new LinkedHashMap<>();m.put("schema",2);m.put("product","Pico");m.put("version","pico");m.put("board",r.getName());m.put("chip",chipName(r.getTarget()));m.put("flashSize",8388608);m.put("files",fs.stream().map(x->{Map<String,Object> q=new LinkedHashMap<>(x);q.put("address",0);return q;}).toList());Files.writeString(j.dir.resolve("manifest.json"),json.writerWithDefaultPrettyPrinter().writeValueAsString(m));j.progress=100;j.status="success"; } catch(Exception e){j.status="failed";j.error=e.getMessage();} }
    private String chipName(String target){return switch(target.toLowerCase(Locale.ROOT)){case "esp32c3"->"ESP32-C3";case "esp32s3"->"ESP32-S3";case "esp32c6"->"ESP32-C6";default->"ESP32";};}
    private String sha(Path p)throws Exception{byte[] h=MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(p));StringBuilder s=new StringBuilder();for(byte b:h)s.append(String.format("%02x",b));return s.toString();}
    private final class Job { final String id; final Path dir; volatile String status="queued",error="",log=""; volatile int progress=0; Job(String id){this.id=id;dir=root.resolve(id).normalize();} Map<String,Object> view(){Map<String,Object>m=new LinkedHashMap<>();m.put("id",id);m.put("status",status);m.put("progress",progress);m.put("log",log);if(!error.isBlank())m.put("error",error);return m;} }
}
