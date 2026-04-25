# Stock Review 详细工作流程

## scan 模式完整流程

1. **前置检查**
   - 确认 `references/up-list.yaml` 配置完整
   - 确认 `data/` 目录可写
   - 确认 ffmpeg、yt-dlp、FunASR 可用

2. **发现视频**
   ```bash
   scripts/discover.py --config references/up-list.yaml \
     --state-file data/state.json \
     --cookies config/cookies.txt \
     --skip-api
   ```
   输出 JSON 数组，包含未处理视频列表。

3. **逐条处理**
   - 调 `state.py mark <bvid> --status discovered`
   - 调 `transcribe.py <file_path> --out-dir data/subtitles --hotwords references/funasr-hotwords.txt`
   - 成功后 `state.py mark <bvid> --status transcribed --method <L1|L2|L3>`
   - 读取 txt，少于 500 字符产出占位报告
   - 否则结合 `review-prompt.md` 生成 markdown 报告
   - 标 `analyzed` → 发送飞书 → 标 `notified` → 标 `done`

4. **汇总**
   - 统计成功/失败数量
   - 发送飞书汇总消息

## 单条模式
- 本地路径：跳过 discover 和 state，直接 transcribe
- B站 URL：yt-dlp 下载后 transcribe

## 飞书发送规则
- 目标：`notify.lark_chat_id`
- 短报告（≤ max_message_chars）：直接发文本
- 长报告：发 markdown 文件

## 状态机
```
discovered → transcribed → analyzed → notified → done
           ↓
         *_err（失败跳过）
```

## 文件命名
- 报告：`data/reports/{YYYY-MM-DD}_{owner_mid}_{title}.md`
- 字幕：`data/subtitles/{sha1[:12]}.srt` / `.txt`