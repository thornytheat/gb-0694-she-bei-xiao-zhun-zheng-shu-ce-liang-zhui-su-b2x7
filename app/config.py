from pathlib import Path
RULE_VERSION = "2026.11.19.1"
TITLE = '设备校准证书与测量追溯'
SHORT = 'calibration-chain'
MODULES = ['证书接收', '设备别名', '有效区间', '量程匹配', '溯源链路', '测量裁决', '撤销复核', '符合性声明']
HEADERS = ['cert', 'device', 'alias', 'parent', 'valid_from', 'valid_to', 'minimum', 'maximum', 'unit', 'revoked', 'measured_at', 'value', 'measure_unit', 'version', 'uncertainty', 'unc_unit', 'coverage_k', 'spec_min', 'spec_max']
SAMPLE = Path(__file__).resolve().parent.parent / "sample_data" / "operations.csv"
LIMIT = 10000
# 声明护基：默认包含因子 k=2（对应约95%包含概率），可按机构规则调整
DECLARATION_COVERAGE_K = 2
