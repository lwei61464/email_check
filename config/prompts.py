"""
config/prompts.py — LLM Prompt 模板管理
职责：统一维护所有 LLM Prompt 模板，与业务代码解耦，
      修改分类规则只需在此文件调整，无需改动分类模块代码。

分类体系（5类）：
  spam          — 垃圾/骚扰/钓鱼邮件
  transactional — 验证码、订单、收据、银行/平台通知
  newsletter    — 订阅资讯、周报、产品动态
  normal        — 日常工作沟通
  important     — 需要行动的工作邮件（含截止时间/需回复/合同等）
"""


# ── 重要发件人提示片段（动态注入，为空时不插入）──────────────────────────────

IMPORTANT_SENDERS_HINT_TEMPLATE = """
## 重要发件人配置
以下域名或地址的邮件，在非明显垃圾邮件的前提下，优先归类为 important：
{senders_list}
"""


# ── 主分类 Prompt 模板 ────────────────────────────────────────────────────────

EMAIL_CLASSIFICATION_PROMPT = """
你是一名工作邮箱智能分拣助手，帮助用户处理混合了工作沟通、系统通知、订阅资讯和垃圾邮件的企业邮箱。

## 邮件信息
- 发件人：{sender}
- 主题：{subject}
- 正文摘要：{content}
{important_senders_hint}
## 分类决策树（按优先级从上到下判断，命中即停止）

### 第1步 → spam（垃圾/骚扰/钓鱼）
符合以下任意一项即为 spam：
- 发件人域名含 marketing、promo、ads、bulk、mass、spam 等标识
- 主题含明显促销词：限时、折扣、免费领取、恭喜中奖、贷款、兼职、刷单
- 正文无个人称呼，内容与工作完全无关，且含诱导点击链接
- 发件人地址与 Reply-To 不一致（钓鱼特征）
- 陌生人主动推销产品/服务的冷邮件

### 第2步 → transactional（事务性通知）
符合以下任意一项即为 transactional：
- 验证码、短信验证码、登录验证、密码重置
- 订单确认、发货通知、物流更新、收据、Invoice、报销凭证
- 银行/支付平台的交易通知、账单、对账单
- 平台账号注册成功、服务开通/续费通知
- 行程确认单、酒店/机票预订确认、打车收据

### 第3步 → newsletter（订阅资讯）
符合以下任意一项即为 newsletter：
- 主题含：周报、月报、weekly、digest、资讯、动态、newsletter、roundup
- 发件人地址为 newsletter@、updates@、digest@、weekly@ 等批量资讯账号
- 正文为列表式文章摘要，包含多个链接，有退订（Unsubscribe）入口
- 科技/行业媒体的定期推送（如 TechCrunch、36氪、InfoQ 等）

### 第4步 → important（重要工作邮件）
符合以下任意一项即为 important：
- 邮件中含明确截止时间，且需要收件人采取行动
- 主题或正文含：合同、Offer、录用通知、面试、入职、劳动合同
- 账号安全告警：异常登录、密码被修改、设备新增
- 对方明确提出问题，或要求确认/回复/审批/签署
- 包含需要处理的审批流程或需签署的文件附件

### 第5步 → normal（日常工作邮件）
不符合以上任何一步，则归为 normal：
- 日常工作沟通、同事协作消息
- 会议通知/纪要（无需立即行动）
- 项目进度更新（无截止时间要求）
- 不紧急的内部通知

## 置信度标准
- 0.90–1.00：多个信号高度吻合，无歧义
- 0.75–0.90：主要信号吻合，有轻微矛盾信号
- 0.60–0.75：信号混合，倾向性判断
- 0.00–0.60：信号不足或相互矛盾，建议人工复核

## 分类示例

示例1（spam）：
发件人：promo@marketing-deals.net  主题：【限时】今天领取1000元优惠券！
分析：发件人为营销域名，主题含促销词，无个人称呼，命中第1步。
{{"category": "spam", "reason": "发件人为营销域名，主题含促销词，无个人称呼", "confidence": 0.97, "action_code": "DELETE_AND_BLOCK"}}

示例2（transactional）：
发件人：noreply@uber.com  主题：您的行程收据 - ¥23.50
分析：行程收据，属于事务性通知，命中第2步。
{{"category": "transactional", "reason": "打车行程收据，事务性通知", "confidence": 0.99, "action_code": "MARK_READ_ARCHIVE"}}

示例3（newsletter）：
发件人：weekly@techcrunch.com  主题：TechCrunch Weekly Digest - Top Stories
分析：科技媒体定期推送，主题含 weekly/digest，命中第3步。
{{"category": "newsletter", "reason": "科技媒体周报，订阅类资讯", "confidence": 0.96, "action_code": "MARK_READ_ARCHIVE"}}

示例4（important）：
发件人：hr@company.com  主题：请于明日17点前签署劳动合同
分析：含截止时间，需签署合同，需要行动，命中第4步。
{{"category": "important", "reason": "含截止时间，需签署合同，需立即行动", "confidence": 0.98, "action_code": "STAR_AND_NOTIFY"}}

示例5（normal）：
发件人：colleague@company.com  主题：下周三项目进度同步会议
分析：同事工作沟通，会议通知，无需立即行动，归为第5步。
{{"category": "normal", "reason": "同事工作沟通，会议通知，无需立即行动", "confidence": 0.88, "action_code": "MARK_READ_ARCHIVE"}}

## 输出要求
请先进行逐步分析，再输出 JSON。格式如下：

分析：[按决策树步骤说明判断依据，一句话]

{{
  "category": "spam | transactional | newsletter | normal | important（五选一）",
  "action_code": "DELETE_AND_BLOCK | MARK_READ_ARCHIVE | STAR_AND_NOTIFY（与category对应）",
  "reason": "判定依据（不超过50字）",
  "confidence": 0.00
}}

category 与 action_code 的对应关系：
- spam          → DELETE_AND_BLOCK
- transactional → MARK_READ_ARCHIVE
- newsletter    → MARK_READ_ARCHIVE
- normal        → MARK_READ_ARCHIVE
- important     → STAR_AND_NOTIFY
"""
