<template>
  <div class="firmware-builder">
    <HeaderBar />
    <main>
      <el-alert v-if="builderChecked && !builderReady" :title="builderError || '编译服务暂不可用，请稍后重试。'" type="warning" :closable="false" />
      <header class="hero"><div class="eyebrow">PICO FIRMWARE BUILDER</div><h1>固件与 USB 刷写</h1><p>选择硬件与功能配置，先由 Pico 服务端编译固件，再连接 USB 写入设备。</p></header>
      <el-alert v-if="!supported" title="请使用 Chrome / Edge，并通过 HTTPS 打开本页面，编译完成后才能使用 Web Serial 刷写。" type="warning" :closable="false" />
      <section class="card"><h2>1 · 选择硬件</h2><p class="hint">配置项来自 Pico 固件仓库的 main/boards，不支持手工输入板型或烧录地址。</p>
        <div class="grid">
          <label>芯片型号<el-select v-model="form.target" @change="targetChanged"><el-option v-for="x in targets" :key="x" :label="x.toUpperCase()" :value="x" /></el-select></label>
          <label>开发板类型<el-select v-model="boardType" filterable @change="typeChanged"><el-option v-for="x in boardTypes" :key="x.board" :label="x.display_name" :value="x.board" /></el-select></label>
          <label>开发板 ID<el-select v-model="form.board" @change="boardChanged"><el-option v-for="x in boardVariants" :key="x.name" :label="x.name" :value="x.board+'#'+x.name" /></el-select></label>
          <label>屏幕型号<el-select v-if="displayOption" v-model="form.options.display_model"><el-option v-for="x in displayOption.choices" :key="x.value" :label="x.label" :value="x.value" /></el-select><el-input v-else value="此板型未提供可选屏幕参数（沿用源码默认）" disabled /></label>
        </div>
        <p class="meta">本机 Pico 源码目录 · {{ boards.length }} 个开发板变体 · 固件 {{ catalogVersion }} · {{ catalogRevision }}</p>
      </section>
      <section class="card"><h2>2 · 基础配置</h2><div class="grid"><label>固件语言<el-select v-model="form.language"><el-option v-for="x in languages" :key="x" :label="x" :value="x" /></el-select></label><label>唤醒词<el-select v-model="form.wakeWord"><el-option label="Hi,ESP（Pico 默认唤醒词）" value="wn9s_hiesp" /><el-option label="Hi,Jason" value="wn9s_hijason" /><el-option label="Hi,乐鑫" value="wn9s_hilexin" /><el-option label="禁用唤醒词" value="disabled" /></el-select></label></div><div v-if="buildOptions.length" class="options"><label v-for="x in extraOptions" :key="x.key">{{ x.label || x.key }}<el-switch v-if="x.type==='boolean'" v-model="form.options[x.key]" /><el-select v-else-if="x.type==='select'" v-model="form.options[x.key]"><el-option v-for="choice in x.choices" :key="choice.value" :label="choice.label" :value="choice.value" /></el-select></label></div></section>
      <section class="card"><h2>3 · 显示、音频与配网</h2><p class="hint">仅显示当前开发板真实支持的编译选项；未修改项沿用开发板默认值。</p><div class="chips"><span v-for="x in capabilities" :key="x">{{ x }}</span></div><label v-if="buildOptions.some(x=>x.key==='wifi_provisioning')" class="wide">Wi‑Fi 配网方式<el-select v-model="form.options.wifi_provisioning"><el-option label="热点配网" value="hotspot" /><el-option label="ESP-BluFi" value="blufi" /></el-select></label></section>
      <section class="card build"><h2>4 · 编译 Pico 固件</h2><p class="hint">编译任务在运行 Pico 服务端的 Mac 上执行，源码、ESP-IDF 和日志不会公开到云端。</p><el-button type="primary" :loading="building" :disabled="!builderReady || building || !form.board" @click="startBuild">{{ building ? '正在编译…' : '编译固件' }}</el-button><el-progress v-if="job" :percentage="job.progress || 0" :status="job.status==='success'?'success':job.status==='failed'?'exception':undefined" /><p v-if="job && ['queued','running'].includes(job.status)" class="meta">{{ buildStageText }}</p><p v-if="job && job.status==='failed' && job.error" class="danger">{{ job.error }}</p><div v-if="job && job.log" class="logpanel">
          <div class="loghead">
            <span class="logtitle">编译日志</span>
            <span class="logstat" :class="'st-'+job.status">{{ job.status==='success'?'成功':job.status==='failed'?'失败':'进行中' }}</span>
            <span class="logmeta">{{ logTotal }} 行</span>
            <span v-if="logErrorCount" class="logmeta logerr">{{ logErrorCount }} 错误</span>
            <span v-if="logWarnCount" class="logmeta logwarn">{{ logWarnCount }} 警告</span>
            <span class="logspacer"></span>
            <button class="logbtn" :class="{on:logFilter==='issues'}" @click="logFilter=logFilter==='issues'?'all':'issues'">{{ logFilter==='issues'?'显示全部':'仅看问题' }}</button>
            <button class="logbtn" @click="copyBuildLog">复制</button>
            <button class="logbtn" @click="logCollapsed=!logCollapsed">{{ logCollapsed?'展开':'收起' }}</button>
          </div>
          <div v-show="!logCollapsed" ref="buildlog" class="logbody" @scroll="onLogScroll">
            <div v-if="!logVisible.length" class="logtrunc">{{ logFilter==='issues'?'没有错误或警告，编译过程干净。':'暂无日志输出' }}</div>
            <div v-else-if="logTruncated" class="logtrunc">已省略较早的 {{ logTruncated }} 行</div>
            <div v-for="l in logVisible" :key="l.n" class="logline" :class="'k-'+l.kind">
              <span class="logln">{{ l.n }}</span><span class="logtx">{{ l.text }}</span>
            </div>
          </div>
          <button v-if="!logCollapsed && !logAutoScroll" class="logjump" @click="jumpLogToEnd">↓ 回到最新</button>
        </div><div v-if="job && job.status==='success'" class="result"><el-button type="success" @click="download('full')">下载完整固件</el-button><el-button v-if="hasArtifact('pico.bin')" @click="download('ota')">下载 OTA 固件</el-button><el-button :disabled="true" @click="loadForFlash">下载后连接 USB 刷写</el-button></div></section>
      <section class="card history"><h2>5 · 固件历史</h2><p class="hint">相同硬件与配置再次编译会直接复用已有固件，不会重复编译。历史记录与产物保存在 Pico 服务端，可直接下载。</p>
        <div class="history-bar"><el-button size="small" :loading="historyLoading" @click="loadHistory">刷新历史</el-button><span class="meta" v-if="history.length">共 {{ history.length }} 条记录</span></div>
        <el-table v-if="history.length" :data="history" size="small" class="history-table">
          <el-table-column label="编译时间" width="170"><template slot-scope="s">{{ formatTime(s.row.created_at) }}</template></el-table-column>
          <el-table-column label="开发板" min-width="170"><template slot-scope="s"><div>{{ (s.row.request && s.row.request.board) || '-' }}</div><small class="meta">ID：{{ (s.row.request && s.row.request.name) || '-' }}</small></template></el-table-column>
          <el-table-column label="芯片" width="100"><template slot-scope="s">{{ s.row.chip || (s.row.request && s.row.request.target) || '-' }}</template></el-table-column>
          <el-table-column label="语言 / 唤醒词" min-width="150"><template slot-scope="s"><div>{{ (s.row.request && s.row.request.language) || '-' }}</div><small class="meta">{{ (s.row.request && s.row.request.wake_word) || '-' }}</small></template></el-table-column>
          <el-table-column label="状态" width="90"><template slot-scope="s"><el-tag :type="s.row.status==='success'?'success':s.row.status==='failed'?'danger':'warning'" size="mini">{{ statusText(s.row.status) }}</el-tag></template></el-table-column>
          <el-table-column label="操作" width="290" align="center" class-name="history-action-cell"><template slot-scope="s">
            <div v-if="s.row.status==='success'" class="history-actions">
              <el-button size="mini" type="danger" plain :loading="deletingId===s.row.id" class="history-delete" @click="removeBuild(s.row)">删除</el-button>
              <el-button v-if="hasFile(s.row,'merged-binary.bin')" size="mini" type="success" plain @click="downloadBuild(s.row,'full')">完整固件</el-button>
              <el-button v-if="hasFile(s.row,'pico.bin')" size="mini" type="primary" plain @click="downloadBuild(s.row,'ota')">OTA</el-button>
              <el-button v-if="s.row.complete!==false" size="mini" type="warning" plain @click="loadHistoryForFlash(s.row)">USB 刷入</el-button>
              <el-button size="mini" plain @click="reuseBuild(s.row)">复用配置</el-button>
            </div>
            <div v-if="s.row.status==='success' && s.row.complete===false" class="history-note"><el-tag size="mini" type="warning">早期记录，无 OTA</el-tag></div>
            <div v-else-if="s.row.status==='failed'" class="history-note">
              <div class="meta">{{ s.row.error || '编译失败' }}</div>
              <el-button size="mini" type="danger" plain :loading="deletingId===s.row.id" class="history-delete" @click="removeBuild(s.row)">删除</el-button>
            </div>
            <div v-else-if="s.row.status!=='success'" class="history-note">
              <div class="meta">{{ statusText(s.row.status) }} · 可删除</div>
              <el-button size="mini" type="danger" plain :loading="deletingId===s.row.id" class="history-delete" @click="removeBuild(s.row)">删除</el-button>
            </div>
          </template></el-table-column>
        </el-table>
        <p v-else-if="!historyLoading" class="meta">暂无历史固件，完成一次编译后会出现在这里。</p>
      </section>
      <section class="card usb"><h2>6 · USB 刷写</h2>
        <p class="hint">通过浏览器 Web Serial 直接写入已校验的分段，按分区擦写，不执行整片擦除。需要 Chrome / Edge 且使用 HTTPS 打开本页。</p>
        <p v-if="flashJob" class="meta">当前固件：<b>{{ flashJob.request && (flashJob.request.board || flashJob.request.name) || flashJob.id }}</b> · {{ manifest && manifest.chip }} · {{ manifest && manifest.files && manifest.files.length }} 个分段</p>
        <div class="flash-steps">
          <el-button :disabled="busy || !flashJob" @click="connect">1 · 连接 USB</el-button>
          <el-button type="danger" :disabled="!connected || busy" @click="flash">2 · 确认并刷入 Pico</el-button>
        </div>
        <el-progress v-if="connected || progress" :percentage="progress" :status="flashStage==='failed'?'exception':['done','manual-reset'].includes(flashStage)?'success':undefined" />
        <p v-if="flashStage!=='idle'" role="status" class="meta">{{ flashStatusText }}</p>
        <p v-if="!['done','manual-reset'].includes(flashStage)" class="meta">{{ connected ? '已识别芯片：'+chip+'（固件要求 '+(manifest && manifest.chip)+'）' : '未连接设备' }}</p>
        <p v-if="connected && manifest && chip !== manifest.chip" class="danger">已连接芯片与固件不匹配，已阻止写入。</p>
        <el-alert v-if="!supported" title="当前浏览器不支持 Web Serial（或页面不是 HTTPS）。请用 Chrome / Edge 打开 https 地址后再刷入。" type="warning" :closable="false" />
      </section>
      <el-dialog title="固件下载" :visible.sync="downloadDialog" :close-on-click-modal="false">
        <p role="status">{{ downloadNotice }}</p>
        <p v-if="downloadUrl"><a :href="downloadUrl" :download="downloadName" target="_blank" rel="noopener">点击保存 {{ downloadName }}</a></p>
        <p v-if="downloadUrl" class="hint">如果应用内浏览器没有弹出下载，请在 Chrome / Edge 中打开本页面后下载。文件已准备好，不需要重新编译。</p>
      </el-dialog>
      <el-alert v-if="error" :title="error" type="error" :closable="false" />
    </main>
  </div>
</template>
<script>
import catalog from '@/generated/firmwareCatalog.json';
import { saveFirmware } from '@/utils/saveFirmware.mjs';
import { firmwareResource } from '@/utils/firmwareDownload.mjs';
import HeaderBar from '@/components/HeaderBar.vue'; import { validateManifest, prepareFirmware, flashPrepared } from '@/utils/picoFirmware.mjs'; import SparkMD5 from 'spark-md5'; import RequestService from '@/apis/httpRequest';
export default {name:'FirmwareCenter',components:{HeaderBar},data:()=>({boardType:'',builderChecked:false,builderReady:false,builderError:'',catalogVersion:catalog.version,catalogRevision:catalog.revision.slice(0,12),supported:false,targets:[],boards:[],languages:['zh-CN','en-US'],form:{target:'',board:'',boardId:'',screenModel:'',language:'zh-CN',wakeWord:'wn9s_hiesp',options:{}},building:false,job:null,manifest:null,parts:null,busy:false,connected:false,chip:'',progress:0,flashStage:'idle',error:'',capabilities:[],buildOptions:[],history:[],historyLoading:false,deletingId:'',downloadDialog:false,downloadBusy:false,downloadNotice:'',downloadUrl:'',downloadName:'',flashJob:null,flashLoading:false,logAutoScroll:true,logCollapsed:false,logFilter:'all'}),computed:{flashStatusText(){return {writing:'正在写入并校验固件…',resetting:'写入与校验完成，正在发送复位信号…',done:'写入与校验完成，已发送复位信号。尚未确认设备启动；若无反应，请按 RST / EN。','manual-reset':'写入与校验完成，但自动复位未完成。请按 RST / EN；若无复位键，请完全断电后重新上电。',failed:'刷写未完成，请查看下方错误。'}[this.flashStage]||''},boardTypes(){return [...new Map(this.filteredBoards.map(b=>[b.board,b])).values()]},boardVariants(){return this.filteredBoards.filter(b=>b.board===this.boardType)},displayOption(){return this.buildOptions.find(o=>o.key==='display_model')},extraOptions(){return this.buildOptions.filter(o=>!['display_model','wifi_provisioning'].includes(o.key))},filteredBoards(){return this.boards.filter(x=>x.target===this.form.target)},selectedBoard(){return this.boards.find(x=>this.form.board===x.board+'#'+x.name)},logLines(){const raw=(this.job&&this.job.log)||'';const arr=raw.split('\n');if(arr.length&&arr[arr.length-1]==='')arr.pop();return arr.map((text,i)=>({n:i+1,text,kind:this.classifyLog(text)}))},
    logVisible(){const t=this.logLines.filter(l=>l.text.trim()!=='');const f=this.logFilter==='issues'?t.filter(l=>l.kind==='error'||l.kind==='warn'||l.kind==='ok'):t;return f.slice(-500)},
    logTotal(){return this.logLines.filter(l=>l.text.trim()!=='').length},
    logTruncated(){const t=this.logLines.filter(l=>l.text.trim()!=='');const n=this.logFilter==='issues'?t.filter(l=>l.kind==='error'||l.kind==='warn'||l.kind==='ok').length:t.length;return Math.max(0,n-500)},
    logErrorCount(){return this.logLines.filter(l=>l.kind==='error').length},
    logWarnCount(){return this.logLines.filter(l=>l.kind==='warn').length},
    buildStageText(){const j=this.job;if(!j)return '';if(j.status==='queued')return '排队中…';if(j.status!=='running')return '';const p=j.progress||0;if(p<60)return '正在准备并下载依赖组件（首次编译较慢，之后会复用缓存）…';if(p<70)return '组件就绪，正在生成构建配置…';return '正在编译并链接固件…'}},mounted(){this.supported=window.isSecureContext&&!!navigator.serial;this.loadBoards();this.loadHistory()},beforeDestroy(){if(this.downloadUrl)URL.revokeObjectURL(this.downloadUrl);if(!this.busy)this.disconnect()},methods:{
    async loadHistory(){
      this.historyLoading=true;
      try{
        const token=JSON.parse(localStorage.getItem('token')||'{}').token;
        const r=await fetch('/pico/firmware-builder/builds',{headers:{Authorization:'Bearer '+token},cache:'no-store'});
        const payload=await r.json(); const data=payload.data || payload;
        if(!r.ok) throw new Error(data.error || ('HTTP '+r.status));
        this.history=Array.isArray(data.builds)?data.builds:[];
      }catch(e){ this.history=[]; }
      finally{ this.historyLoading=false; }
    },
    async artifactSize(row,name){ try{ const f=(row.files||[]).find(x=>x.name===name); if(f&&f.size) return f.size }catch(e){} return 0 },
    statusText(s){return s==='success'?'成功':s==='failed'?'失败':s==='running'?'编译中':'排队中'},
    formatTime(t){ if(!t) return '-'; const d=new Date(t); return isNaN(d.getTime())?t:d.toLocaleString('zh-CN',{hour12:false}) },
    hasFile(row,name){ return !!(row.files||[]).some(f=>f.name===name && f.available!==false) },
    hasArtifact(name){ const fs=(this.job&&this.job.manifest&&this.job.manifest.files)||[]; return fs.some(f=>f.name===name) },
    async loadManifestForJob(){ if(!this.job||!this.job.id) return; try{ const r=await firmwareResource(this.job.id,'manifest',{token:localStorage.getItem('token')}); this.job=Object.assign({},this.job,{manifest:await r.json()}) }catch(e){} },
    async loadHistoryForFlash(row){
      this.error='';this.flashStage='idle';this.flashJob=row;this.progress=0;this.chip='';this.connected=false;
      try{
        this.manifest=null;this.parts=null;
        const options={token:localStorage.getItem('token')};
        const response=await firmwareResource(row.id,'manifest',options);
        const manifest=validateManifest(await response.json());
        const files=[];
        for(const f of manifest.files){
          const r=await firmwareResource(row.id,'artifact/'+f.name,options);
          files.push(new File([await r.blob()],f.name));
        }
        this.parts=await prepareFirmware(manifest,files);this.manifest=manifest;
        this.$message.success('固件已校验，请连接 USB 后刷入');
        this.$nextTick(()=>{const el=this.$el.querySelector('.usb');if(el)el.scrollIntoView({behavior:'smooth'})});
      }catch(e){this.error='固件载入失败：'+e.message}
    },
    async downloadBuild(row,kind){
      if(this.downloadBusy) return;
      this.error='';this.downloadBusy=true;this.downloadDialog=true;
      this.downloadNotice='正在准备固件，请稍候…';
      if(this.downloadUrl) URL.revokeObjectURL(this.downloadUrl);
      this.downloadUrl='';this.downloadName='';
      try{
        const name=kind==='full'?'merged-binary.bin':'pico.bin';
        const bytes=await this.artifactSize(row,name);
        this.downloadNotice=bytes?('正在下载 '+name+'（'+(bytes/1048576).toFixed(1)+' MB），大文件经云端转发可能需要十几秒，请勿关闭窗口…'):('正在下载 '+name+'，请勿关闭窗口…');
        const result=await saveFirmware(row.id,name,{token:localStorage.getItem('token')});
        if(result.cancelled){this.downloadNotice='已取消保存';return;}
        if(result.saved){this.downloadNotice='固件已保存到你选择的位置';return;}
        this.downloadUrl=result.url;this.downloadName=name;
        this.downloadNotice='固件已就绪，已请求浏览器下载。如未开始，请点击下方保存链接。';
      }catch(e){this.error=e.message;this.downloadNotice='下载失败：'+e.message;}
      finally{this.downloadBusy=false;}
    },
    async removeBuild(row){
      if(!row || !row.id || this.deletingId) return;
      try{
        await this.$confirm('将删除这条编译记录、磁盘上的全部固件产物，并清除可复用缓存。删除后无法恢复，下次需重新编译。','彻底删除固件',{type:'warning',confirmButtonText:'彻底删除',cancelButtonText:'取消'});
      }catch(e){ return; }
      this.deletingId=row.id; this.error='';
      try{
        const token=JSON.parse(localStorage.getItem('token')||'{}').token;
        const r=await fetch('/pico/firmware-builder/build/'+encodeURIComponent(row.id),{method:'DELETE',headers:{Authorization:'Bearer '+token}});
        if(!r.ok){ let msg='HTTP '+r.status; try{ const d=await r.json(); msg=(d && (d.msg||d.error))||msg; }catch(e){} throw new Error(msg); }
        if(this.flashJob && this.flashJob.id===row.id){ this.flashJob=null; this.manifest=null; this.parts=null; this.connected=false; this.progress=0; }
        this.history=this.history.filter(x=>x.id!==row.id);
        this.$message.success('已彻底删除该固件');
      }catch(e){ this.error='删除失败：'+e.message; }
      finally{ this.deletingId=''; }
    },
    async removeBuild(row){
      try{
        await this.$confirm('将永久删除这条编译记录、磁盘上的固件产物和对应缓存，删除后再次编译会重新执行完整编译。','确认清理固件',{type:'warning',confirmButtonText:'清理',confirmButtonClass:'el-button--danger'});
      }catch(e){return}
      this.deletingId=row.id;this.error='';
      try{
        const token=JSON.parse(localStorage.getItem('token')||'{}').token;
        const r=await fetch('/pico/firmware-builder/build/'+row.id,{method:'DELETE',headers:{Authorization:'Bearer '+token}});
        const payload=await r.json().catch(()=>({}));
        const data=payload.data||payload;
        if(!r.ok||payload.code>=400) throw new Error((payload&&payload.msg)||data.error||('HTTP '+r.status));
        const freed=data.freed_bytes?('，释放 '+(data.freed_bytes/1048576).toFixed(1)+' MB'):'';
        this.$message.success('已清理固件记录与产物'+freed);
        if(this.flashJob&&this.flashJob.id===row.id){this.flashJob=null;this.manifest=null;this.parts=null;this.connected=false}
        await this.loadHistory();
      }catch(e){this.error='清理失败：'+e.message}
      finally{this.deletingId=''}
    },
    classifyLog(line){const t=(line||'').trim();if(!t)return 'dim';
      if(/\b(fatal|error|failed|failure|exception|traceback|undefined reference)\b/i.test(t))return 'error';
      if(/\b(warn|warning|deprecated|obsolete)\b/i.test(t))return 'warn';
      if(/^NOTE:\s*\[\d+\/\d+\]/.test(t)||/^\[\d+\/\d+\]/.test(t))return 'step';
      if(/^(Successfully|Build complete|Project build complete|Generated default assets|To flash|Flash binary)/i.test(t))return 'ok';
      if(/^(python -m esptool|ninja|cmake|idf\.py|cd )/.test(t))return 'cmd';
      return 'info'},
    onLogScroll(e){const el=e.target;this.logAutoScroll=(el.scrollHeight-el.scrollTop-el.clientHeight)<40},
    jumpLogToEnd(){this.logAutoScroll=true;this.scrollBuildLog()},
    copyBuildLog(){const t=(this.job&&this.job.log)||'';if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(t).then(()=>this.$message.success('编译日志已复制'),()=>this.$message.warning('复制失败，请手动选择日志内容'))}else{this.$message.warning('当前浏览器不支持一键复制')}},
    scrollBuildLog(){if(!this.logAutoScroll)return;this.$nextTick(()=>{const el=this.$refs.buildlog;if(el)el.scrollTop=el.scrollHeight})},
    reuseBuild(row){
      const q=row.request||{};
      if(q.target && this.targets.includes(q.target)){ this.form.target=q.target; this.targetChanged(); }
      if(q.board){ const match=this.boards.find(b=>b.board===q.board && b.name===q.name); if(match){ this.boardType=match.board; this.form.board=match.board+'#'+match.name; this.boardChanged(); } }
      if(q.language) this.form.language=q.language;
      if(q.wake_word) this.form.wakeWord=q.wake_word;
      const opts=(q.build_options&&typeof q.build_options==='object')?q.build_options:{};
      Object.keys(opts).forEach(k=>{ if(k in this.form.options) this.form.options[k]=opts[k]; });
      this.$message.success('已载入历史配置，可再次编译或下载');
      window.scrollTo({top:0,behavior:'smooth'});
    },
    async loadBoards(){
      try {
        if(!catalog.boards.length) throw new Error('本机源码清单为空，请重新生成硬件目录');
        this.boards=catalog.boards;this.languages=catalog.languages;
        this.targets=[...new Set(this.boards.map(x=>x.target))];
        this.form.target=this.targets.includes('esp32c3')?'esp32c3':this.targets[0];this.targetChanged();this.checkBuilder();
      } catch(e){this.error='硬件目录加载失败：'+e.message}
    },
    targetChanged(){this.boardType=this.filteredBoards.find(x=>x.board==='folotoy/ai-passport')?.board || this.filteredBoards[0]?.board || '';this.typeChanged()},
    typeChanged(){const b=this.boardVariants[0];this.form.board=b?b.board+'#'+b.name:'';this.boardChanged()},
    boardChanged(){const x=this.selectedBoard;this.form.options={};this.buildOptions=x?.build_options||[];this.buildOptions.forEach(o=>this.$set(this.form.options,o.key,o.default));this.form.boardId=x?.name||'';this.capabilities=[];if(x&&!x.wake_word_supported)this.form.wakeWord='disabled'},
    async startBuild(){if(!this.builderReady){await this.checkBuilder();if(!this.builderReady)return}this.building=true;this.error='';this.job=null;this.logAutoScroll=true;this.logCollapsed=false;try{const token=JSON.parse(localStorage.getItem('token')||'{}').token;const [board,name]=this.form.board.split('#');const r=await fetch('/pico/firmware-builder/build',{method:'POST',headers:{'content-type':'application/json',Authorization:'Bearer '+token},body:JSON.stringify({board,name,target:this.form.target,language:this.form.language,wakeWord:this.form.wakeWord,buildOptions:this.form.options})});if(!r.ok)throw new Error(await r.text());const payload=await r.json();this.job=payload.data || payload;this.poll()}catch(e){this.error=e.message}finally{this.building=false}},async checkBuilder(){
      try {
        const token=JSON.parse(localStorage.getItem('token')||'{}').token;
        const r=await fetch('/pico/firmware-builder/health',{headers:{Authorization:'Bearer '+token}});
        const payload=await r.json(); const data=payload.data || payload;
        if(!r.ok || data.status!=='ready') throw new Error(data.error || '编译服务未就绪');
        this.builderReady=true; this.builderError='';
      } catch(e) {
        this.builderReady=false; this.builderError='编译服务暂不可用：'+e.message;
      } finally { this.builderChecked=true; }
    },async poll(){if(!this.job)return;const token=JSON.parse(localStorage.getItem('token')||'{}').token;const r=await fetch('/pico/firmware-builder/build/'+this.job.id,{headers:{Authorization:'Bearer '+token}});const payload=await r.json();this.job=payload.data || payload;this.scrollBuildLog();if(['queued','running'].includes(this.job.status)){this.building=true;setTimeout(()=>this.poll(),1500)}else{this.building=false;if(this.job.status==='success'){await this.loadManifestForJob();this.loadHistory()}}},async download(kind){return this.downloadBuild(this.job,kind)},async loadForFlash(){
      this.error=''; this.parts=null; this.manifest=null;
      try {
        const options={token:localStorage.getItem('token')};
        const response=await firmwareResource(this.job.id,'manifest',options);
        const manifest=validateManifest(await response.json());
        const files=[];
        for(const f of manifest.files){
          const r=await firmwareResource(this.job.id,'artifact/'+f.name,options);
          files.push(new File([await r.blob()],f.name));
        }
        this.parts=await prepareFirmware(manifest,files); this.manifest=manifest;
      } catch(e){this.error=e.message}
    },async connect(){try{const port=await navigator.serial.requestPort();const {ESPLoader,Transport}=await import('esptool-js');this.transport=new Transport(port);this.loader=new ESPLoader({transport:this.transport,baudrate:460800,terminal:{clean:()=>{},write:()=>{},writeLine:()=>{}}});await this.loader.main();this.chip=this.loader.chip.CHIP_NAME;this.connected=true}catch(e){this.error=e.message;await this.disconnect()}},async disconnect(){try{if(this.transport)await this.transport.disconnect()}catch(e){}this.transport=null;this.loader=null;this.connected=false;this.chip=''},async flash(){
      this.busy=true;
      try {
        await this.$confirm('确认板型与备份后继续写入？','确认刷入 Pico',{type:'warning'});
      } catch (_) { this.busy=false; return; }
      this.error='';this.progress=0;this.flashStage='writing';
      try {
        const sizes=this.parts.map(p=>p.data.length),total=sizes.reduce((a,b)=>a+b,0);
        const result=await flashPrepared(this.loader,this.manifest,this.parts,{
          confirmed:true,
          onStage:stage=>{this.flashStage=stage},
          calculateMD5Hash:d=>SparkMD5.ArrayBuffer.hash(d.buffer.slice(d.byteOffset,d.byteOffset+d.byteLength)),
          reportProgress:(i,w,t)=>{this.progress=Math.min(99,Math.floor(100*(sizes.slice(0,i).reduce((a,b)=>a+b,0)+sizes[i]*w/t)/total))}
        });
        this.progress=100;
        this.flashStage=result.resetRequested?'done':'manual-reset';
      } catch(e) {this.error=e.message;this.flashStage='failed'}
      finally {await this.disconnect();this.busy=false}
    }}};
</script>
<style scoped>.firmware-builder{min-height:100vh;background:#f1f5fa;color:#18243a}.firmware-builder main{max-width:1100px;margin:auto;padding:30px 24px 80px}.hero{text-align:center;padding:25px}.eyebrow{letter-spacing:3px;color:#6c7e98;font-size:12px}.hero h1{font-size:36px;margin:14px}.hero p,.hint{color:#60708a}.card{background:#fff;border:1px solid #dce5ef;border-radius:16px;padding:28px;margin:18px 0;box-shadow:0 3px 12px #2b46650d}.card h2{margin:0 0 15px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:24px}label{display:flex;flex-direction:column;gap:8px;font-weight:600;margin:14px 0}.el-select,.el-input{width:100%}.meta{color:#59708e}.options{display:grid;grid-template-columns:1fr 1fr;gap:12px}.options label{flex-direction:row;align-items:center;justify-content:space-between}.chips span{display:inline-block;padding:8px 14px;background:#edf3fa;border-radius:18px;margin:5px;color:#426080}.wide{max-width:48%}.logpanel{position:relative;margin-top:16px;border:1px solid #22304a;border-radius:12px;overflow:hidden;background:#0f1622;box-shadow:0 6px 18px #0f162226}.loghead{display:flex;align-items:center;gap:10px;padding:9px 12px;background:#151f30;border-bottom:1px solid #22304a;color:#c7d3e6;font-size:12px}.logtitle{font-weight:600;color:#e8eefb;letter-spacing:.4px}.logstat{padding:1px 8px;border-radius:999px;font-size:11px;font-weight:600}.logstat.st-running{background:#2a3f63;color:#9dc4ff}.logstat.st-success{background:#1d4630;color:#7fe0a5}.logstat.st-failed{background:#4d2026;color:#ff9ba6}.logmeta{color:#8296b3}.logmeta.logerr{color:#ff9ba6}.logmeta.logwarn{color:#ffcf87}.logspacer{flex:1}.logbtn{border:1px solid #2f3f5c;background:#1b2739;color:#c7d3e6;border-radius:7px;padding:3px 10px;font-size:12px;cursor:pointer;transition:.15s}.logbtn:hover{background:#26364f;border-color:#3d5a86;color:#fff}.logbtn.on{background:#1f61c4;border-color:#2a72e0;color:#fff}.logbody{max-height:300px;overflow:auto;padding:8px 0;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12px;line-height:1.55}.logtrunc{padding:4px 14px 8px;color:#6d7f9c;font-style:italic}.logline{display:flex;padding:0 14px;white-space:pre-wrap;word-break:break-word}.logline:hover{background:#17202f}.logln{flex:0 0 46px;text-align:right;padding-right:14px;color:#4d6183;user-select:none}.logtx{flex:1;color:#c3d0e4}.logline.k-error .logtx{color:#ff8a96}.logline.k-error{background:#3a1a2066}.logline.k-warn .logtx{color:#ffcf87}.logline.k-step .logtx{color:#8fa6c4}.logline.k-ok .logtx{color:#79e2a4;font-weight:600}.logline.k-cmd .logtx{color:#c99cf5}.logline.k-dim .logtx{color:#5d6f8c}.logjump{position:absolute;right:16px;bottom:14px;border:1px solid #3d5a86;background:#1f61c4;color:#fff;border-radius:999px;padding:4px 12px;font-size:12px;cursor:pointer;box-shadow:0 4px 12px #0006}.logjump:hover{background:#2a72e0}.danger{color:#c0392b;font-weight:600}.result{margin-top:20px}.history-bar{display:flex;align-items:center;gap:14px;margin-bottom:14px}.history-table{width:100%}.history-table .meta{color:#7c8ba1;font-size:12px}.history .meta{color:#7c8ba1}.history-actions{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px}.history-actions .el-button{width:100%;margin:0}.history-actions .history-delete{order:-1}.history-actions .el-button{width:100%;margin:0}.history-note{margin-top:6px}.history-action-cell .cell{overflow:visible}@media(max-width:700px){.grid,.options{grid-template-columns:1fr}.wide{max-width:100%}}</style>
