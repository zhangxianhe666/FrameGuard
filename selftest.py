"""端到端自测：生成演示图片 → 调用真实模型分析 → 生成报告。"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.config import ModelConfig
from core.demo import generate_demo_frames
from core.pipeline import JobRunner, JobSettings
from core.prompt import load_default_template

RULES = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "rules", "default_rules.md"),
             encoding="utf-8").read()

# 演示场景只覆盖安全帽 / 手机 / 工具三项，收缩规则以加快自测
TEST_RULES = """# 识别规则

### 1. 是否所有人员都佩戴安全帽
- 合法取值：是 / 否
- 违规取值：否
- 判定标准：观察图像中所有可见人员的头部，只要存在任意一名人员头部未佩戴安全帽即判定为「否」；画面中无人时判定为「是」。

### 2. 是否存在人员在岗使用手机
- 合法取值：是 / 否
- 违规取值：是
- 判定标准：若图像中存在人员手持手机、低头注视手机屏幕或贴近耳部通话，判定为「是」；否则判定为「否」。画面中无人时判定为「否」。

### 3. 是否存在无人看管的作业工具
- 合法取值：是 / 否
- 违规取值：是
- 判定标准：若图像中存在电钻、扳手等作业工具被随意放置在地面或设备旁，且周边无人在岗看管，判定为「是」；工具收纳在工具箱中或紧邻作业人员时判定为「否」。
"""


def main() -> None:
    demo_dir = generate_demo_frames(6)
    print(f"[1/3] 演示图片目录：{demo_dir}")

    settings = JobSettings(
        source=demo_dir,
        source_type="图片目录",
        interval_sec=60,
        rules_text=TEST_RULES,
        template=load_default_template(),
        extra_context="该画面为合成演示图形。",
        model=ModelConfig(model="InternVL3.5-241B-A28B", temperature=0.1),
        workers=3,
        period="30min",
        include_thumbnails=True,
    )
    runner = JobRunner(settings)
    print("[2/3] 开始分析……")
    started = time.time()
    for log, report in runner.run():
        print("   ", log)
    print(f"[3/3] 总耗时 {time.time() - started:.1f} 秒")
    print("输出文件：")
    for key, path in (runner.output_paths or {}).items():
        print(f"   {key}: {path}")

    if runner.report:
        report = runner.report
        print(f"\n结果：总 {report.total} 帧，成功 {report.succeeded}，失败 {report.failed}，违规 {report.violation_count}")
        for r in report.results:
            values = {k: v for k, v in r.parsed.items() if not k.startswith("__")}
            print(f"  {r.frame.time_str('%H:%M:%S')} ok={r.ok} 违规={r.violations}")
            if not r.ok:
                print(f"      错误：{r.error}")
            else:
                print(f"      {str(values)[:260]}")


if __name__ == "__main__":
    main()
