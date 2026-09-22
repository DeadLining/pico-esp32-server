<template>
  <div class="welcome">
    <HeaderBar />
    <div class="main-wrapper">
      <div class="content-panel">
        <div class="content-area" v-loading="loading">
          <el-card class="settings-card" shadow="never">
            <div class="operation-header">
              <h2 class="page-title">{{ $t('systemSettings.pageTitle') }}</h2>
              <div class="right-operations">
                <CustomButton icon="el-icon-refresh" @click="fetchParams">
                  {{ $t('systemSettings.reload') }}
                </CustomButton>
                <CustomButton type="confirm" icon="el-icon-check" :disabled="saving" @click="saveAll">
                  {{ saving ? $t('systemSettings.saving') : $t('systemSettings.save') }}
                </CustomButton>
              </div>
            </div>

            <el-alert
              :title="$t('systemSettings.hint')"
              type="info"
              :closable="false"
              show-icon
              style="margin-bottom: 20px"
            />

            <el-form label-width="180px" label-position="left">
              <template v-for="group in visibleGroups">
                <div :key="group.key" class="settings-group">
                  <div class="group-title">{{ $t(group.titleKey) }}</div>
                  <el-form-item
                    v-for="field in group.fields"
                    :key="field.code"
                    :label="$t(field.labelKey)"
                  >
                    <el-switch
                      v-if="field.type === 'boolean'"
                      v-model="form[field.code]"
                      :active-value="'true'"
                      :inactive-value="'false'"
                    />
                    <el-input
                      v-else
                      v-model="form[field.code]"
                      :type="field.secret ? 'password' : 'text'"
                      :show-password="field.secret"
                      :placeholder="field.placeholder"
                      @focus="handleFocus(field)"
                      @blur="handleBlur(field)"
                    />
                    <div v-if="field.hintKey" class="field-hint">{{ $t(field.hintKey) }}</div>
                    <div v-if="field.secret && masked[field.code]" class="field-hint">
                      {{ $t('systemSettings.secretUnchanged') }}
                    </div>
                  </el-form-item>
                </div>
              </template>
            </el-form>
          </el-card>
        </div>
      </div>
    </div>
    <el-footer>
      <version-footer />
    </el-footer>
  </div>
</template>

<script>
import Api from '@/apis/api';
import HeaderBar from '@/components/HeaderBar.vue';
import VersionFooter from '@/components/VersionFooter.vue';
import CustomButton from '@/components/CustomButton.vue';

const FIELD_GROUPS = [
  {
    key: 'basic',
    titleKey: 'systemSettings.groupBasic',
    fields: [
      { code: 'server.name', labelKey: 'systemSettings.serverName', type: 'string', placeholder: 'Pico', hintKey: 'systemSettings.serverNameHint' },
      { code: 'server.fronted_url', labelKey: 'systemSettings.frontendUrl', type: 'string', placeholder: 'https://your-domain', hintKey: 'systemSettings.frontendUrlHint' },
      { code: 'server.auth.enabled', labelKey: 'systemSettings.authEnabled', type: 'boolean', hintKey: 'systemSettings.authEnabledHint' },
    ],
  },
  {
    key: 'connect',
    titleKey: 'systemSettings.groupConnect',
    fields: [
      { code: 'server.websocket', labelKey: 'systemSettings.websocket', type: 'string', placeholder: 'wss://host/pico/v1/', hintKey: 'systemSettings.websocketHint' },
      { code: 'server.ota', labelKey: 'systemSettings.ota', type: 'string', placeholder: 'https://host/pico/ota/', hintKey: 'systemSettings.otaHint' },
    ],
  },
  {
    key: 'security',
    titleKey: 'systemSettings.groupSecurity',
    fields: [
      { code: 'server.secret', labelKey: 'systemSettings.serverSecret', type: 'string', secret: true, hintKey: 'systemSettings.serverSecretHint' },
    ],
  },
  {
    key: 'ice',
    titleKey: 'systemSettings.groupIce',
    fields: [
      { code: 'server.beian_icp_num', labelKey: 'systemSettings.beianIcp', type: 'string' },
      { code: 'server.beian_ga_num', labelKey: 'systemSettings.beianGa', type: 'string' },
    ],
  },
];

export default {
  name: 'SystemSettings',
  components: { HeaderBar, VersionFooter, CustomButton },
  data() {
    return {
      loading: false,
      saving: false,
      form: {},
      original: {},
      masked: {},
    };
  },
  computed: {
    visibleGroups() {
      return FIELD_GROUPS.filter(group =>
        group.fields.some(field => Object.prototype.hasOwnProperty.call(this.form, field.code))
      );
    },
    allFieldCodes() {
      return FIELD_GROUPS.reduce((acc, group) => acc.concat(group.fields.map(f => f.code)), []);
    },
  },
  created() {
    this.fetchParams();
  },
  methods: {
    fetchParams() {
      this.loading = true;
      const collect = (page, collected) => {
        Api.admin.getParamsList({ page, limit: 500, paramCode: '' }, ({ data }) => {
          if (data.code !== 0) {
            this.loading = false;
            this.$message.error(data.msg || this.$t('systemSettings.loadFailed'));
            return;
          }
          const payload = data.data || {};
          const list = payload.list || [];
          const merged = collected.concat(list);
          const total = Number(payload.total) || merged.length;
          if (merged.length < total && list.length > 0) {
            collect(page + 1, merged);
            return;
          }
          this.loading = false;
          const nextForm = {};
          const nextOriginal = {};
          this.masked = {};
          merged.forEach(item => {
            if (this.allFieldCodes.includes(item.paramCode)) {
              const value = item.paramValue == null ? '' : String(item.paramValue);
              nextForm[item.paramCode] = value;
              nextOriginal[item.paramCode] = value;
              if (/[*]/.test(value)) {
                this.$set(this.masked, item.paramCode, true);
              }
            }
          });
          this.form = nextForm;
          this.original = nextOriginal;
        });
      };
      collect(1, []);
    },
    handleFocus(field) {
      if (field.secret && this.masked[field.code] && /[*]/.test(this.form[field.code] || '')) {
        this.$set(this.form, field.code, '');
      }
    },
    handleBlur(field) {
      if (field.secret && this.masked[field.code] && !this.form[field.code]) {
        this.$set(this.form, field.code, this.original[field.code] || '');
      }
    },
    saveAll() {
      const changed = this.allFieldCodes.filter(code =>
        Object.prototype.hasOwnProperty.call(this.form, code) &&
        this.form[code] !== this.original[code]
      );
      if (changed.length === 0) {
        this.$message.info(this.$t('systemSettings.noChange'));
        return;
      }
      this.saving = true;
      const tasks = changed.map(code => new Promise(resolve => {
        Api.admin.updateParam(
          { paramCode: code, paramValue: this.form[code] },
          ({ data }) => resolve({ code, ok: data.code === 0, msg: data.msg }),
          ({ data }) => resolve({ code, ok: false, msg: data && data.msg })
        );
      }));
      Promise.all(tasks).then(results => {
        this.saving = false;
        const failed = results.filter(r => !r.ok);
        if (failed.length === 0) {
          this.$message.success(this.$t('systemSettings.saveSuccess'));
          this.fetchParams();
        } else {
          this.$message.error(
            this.$t('systemSettings.savePartialFailed', { count: failed.length })
          );
          this.fetchParams();
        }
      });
    },
  },
};
</script>

<style lang="scss" scoped>
.welcome {
  min-height: 100vh;
  background: #eff4ff;
  display: flex;
  flex-direction: column;
}
.main-wrapper {
  flex: 1;
  margin: 0 22px;
}
.content-area {
  height: 100%;
}
.settings-card {
  border-radius: 15px;
  min-height: 60vh;
}
.operation-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.page-title {
  font-size: 24px;
  margin: 0;
}
.right-operations {
  display: flex;
  gap: 12px;
}
.settings-group {
  margin-bottom: 24px;
  padding: 16px 20px;
  background: #f8faff;
  border-radius: 10px;
}
.group-title {
  font-size: 16px;
  font-weight: 600;
  color: #34495e;
  margin-bottom: 12px;
}
.field-hint {
  font-size: 12px;
  color: #8d99ab;
  line-height: 1.6;
  margin-top: 4px;
}
</style>
