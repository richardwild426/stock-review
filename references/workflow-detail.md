# Stock Review 详细工作流程

## scan 模式完整流程

1. **前置检查**
   - 确认 `references/up-list.yaml` 配置完整
   - 确认 `data/` 目录可写
   - 确认 ffmpeg、yt-dlp、FunASR 可用

2. **发现视频**
   ```bash
   scripts/discover.py --config references/up-list.yaml \
     --state-file data/state.json
   ```
   输出 JSON 数组，包含未处理视频列表。已在终态或重试次数达上限的条目自动跳过。

3. **逐条处理**（按 `state.py get <bvid>` 当前 status 续跑，不要回退）
   - 无记录 / `*_err`：`state.py mark <bvid> --status discovered`
   - status == `discovered`：
     - 调 `transcribe.py <file_path> --out-dir data/subtitles --hotwords references/funasr-hotwords.txt`
     - 成功 → `state.py mark <bvid> --status transcribed --method <L1|L2|L3>`
     - 失败 → `state.py mark <bvid> --status transcribe_err --error "<msg>"`，跳过本条
   - status == `transcribed`：
     - 读取 txt；少于 500 字符产出占位报告，否则结合 `review-prompt.md` 生成 markdown
     - `state.py mark <bvid> --status analyzed --report <path>`
   - status == `analyzed`：发送飞书 → `state.py mark <bvid> --status notified`
   - status == `notified`：`state.py mark <bvid> --status done`

4. **汇总**
   - 统计成功/失败数量
   - 发送飞书汇总消息

## 单条模式
- 本地路径：跳过 discover 和 state，直接 transcribe
- B站 URL：先 yt-dlp 下载到 `data/videos/`，再 transcribe
  ```bash
  yt-dlp -f bv*+ba/best --merge-output-format mp4 \
    -o 'data/videos/%(id)s.%(ext)s' \
    --cookies config/cookies.txt <URL>
  ```

## 飞书发送规则
- 目标：`notify.lark_chat_id`
- 短报告（≤ max_message_chars）：直接发文本
- 长报告：发 markdown 文件

## 状态机
```
(new) → discovered → transcribed → analyzed → notified → done
                  ↓            ↓           ↓          ↓
              *_err（失败标记后跳过当轮，下轮 discover 重新返回，retry_count++）
```
- 终态：`done`、`skipped_too_short`、`skipped_no_audio`（discover 不再返回）
- 中间态：`discovered`/`transcribed`/`analyzed`/`notified`（discover 仍返回，附 `_state`，工作流按现状续跑）
- `retry_count >= discover.max_retries`（默认 3）的条目永久不再返回；如需手工重跑，编辑 `data/state.json` 把对应 `retry_count` 清零

## 文件命名
- 报告：`data/reports/{YYYY-MM-DD}_{owner_mid}_{title}.md`
- 字幕：`data/subtitles/{sha1[:12]}.srt` / `.txt`