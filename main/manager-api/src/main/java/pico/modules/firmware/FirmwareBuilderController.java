package pico.modules.firmware;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import lombok.Data;
import lombok.RequiredArgsConstructor;
import pico.common.utils.Result;

@RestController
@RequestMapping("/firmware-builder")
@Tag(name = "Pico 固件编译")
@RequiredArgsConstructor
public class FirmwareBuilderController {
    private final FirmwareBuilderService service;

    @GetMapping("/health")
    @Operation(summary = "检查 Pico 固件编译服务")
    public Result<Map<String, Object>> health() { return new Result<Map<String, Object>>().ok(service.health()); }

    @GetMapping("/boards")
    @Operation(summary = "读取 Pico 固件板型清单")
    public Result<Map<String, Object>> boards() { return new Result<Map<String, Object>>().ok(service.boards()); }

    @PostMapping("/build")
    @Operation(summary = "创建 Pico 固件编译任务")
    public Result<Map<String, Object>> build(@Valid @RequestBody BuildRequest request) {
        return new Result<Map<String, Object>>().ok(service.create(request));
    }

    @GetMapping("/builds")
    @Operation(summary = "读取 Pico 固件编译历史")
    public Result<Map<String, Object>> builds() { return new Result<Map<String, Object>>().ok(service.builds()); }

    @GetMapping("/build/{id}")
    public Result<Map<String, Object>> status(@PathVariable String id) { return new Result<Map<String, Object>>().ok(service.status(id)); }

    @DeleteMapping("/build/{id}")
    @Operation(summary = "删除 Pico 固件编译记录及其产物")
    public Result<Map<String, Object>> delete(@PathVariable String id) { return new Result<Map<String, Object>>().ok(service.delete(id)); }

    @GetMapping("/build/{id}/manifest")
    public ResponseEntity<Resource> manifest(@PathVariable String id) { try { return ResponseEntity.ok().contentType(MediaType.APPLICATION_JSON).body(new org.springframework.core.io.ByteArrayResource(service.builderManifest(id))); } catch (IOException e) { return ResponseEntity.notFound().build(); } }

    @GetMapping("/build/{id}/artifact/{name:.+}")
    public ResponseEntity<Resource> artifact(@PathVariable String id, @PathVariable String name) {
        if (!name.matches("[a-zA-Z0-9._-]+") || name.contains("..")) return ResponseEntity.badRequest().build();
        try { return ResponseEntity.ok().contentType(MediaType.APPLICATION_OCTET_STREAM).header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=\"" + name + "\"").body(new org.springframework.core.io.ByteArrayResource(service.builderFile(id,name))); } catch (IOException e) { return ResponseEntity.notFound().build(); }
    }

    private ResponseEntity<Resource> file(Path path, String name, MediaType type) {
        if (path == null || !Files.isRegularFile(path)) return ResponseEntity.notFound().build();
        return ResponseEntity.ok().contentType(type).header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=\"" + name + "\"").body(new FileSystemResource(path));
    }

    @Data
    public static class BuildRequest {
        @NotBlank private String board;
        @NotBlank private String name;
        @NotBlank private String target;
        @NotBlank private String language;
        @NotBlank private String wakeWord;
        private Map<String, Object> buildOptions;
    }
}
