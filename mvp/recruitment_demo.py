"""Standalone recruitment example, in the style of parlant/examples/healthcare.py.

Run from the repository root after installing the MVP runtime dependencies:
    uv run --project mvp --extra runtime python mvp/recruitment_demo.py

Open http://localhost:8800/chat as a candidate, and /hr as a human recruiter.
Only Parlant serves the chat: no CATS API, worker, compiler or PostgreSQL.
Jobs/FAQ load from data/recruitment-demo; profiles and mock CRM persist as JSON.
Parlant sessions/customers persist locally too. SDK cache/logs use mvp/.runtime/recruitment-demo.
The standalone demo keeps its own guidelines and application journey.
Tool calls are printed without candidate data; native events are available in Parlant.
The CATS worker's response validation/retry guarantees are outside this demo.
"""

import asyncio
import os
import re
import unicodedata
from functools import partial
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

# Prepare the provider and a separate data directory before importing the SDK.
load_dotenv(Path(__file__).with_name(".env"))
RUNTIME_DIR = Path(
    os.environ.get(
        "CATS_DEMO_RUNTIME_DIR", str(Path(__file__).parent / ".runtime" / "recruitment-demo")
    )
)
os.environ["PARLANT_HOME"] = str(RUNTIME_DIR)
os.environ.setdefault("HF_HOME", str(Path(__file__).parent / ".runtime" / "huggingface"))
os.environ.setdefault("HF_MODULES_CACHE", str(Path(__file__).parent / ".runtime" / "hf_modules"))
if os.environ.get("CATS_EMBEDDING_DEVICE", "cpu") == "cpu":
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
os.environ.setdefault("LITELLM_ENABLE_THINKING", "false")
os.environ.setdefault("LITELLM_MAX_TOKENS", "5000")
os.environ["LITELLM_PROVIDER_BASE_URL"] = os.environ.get(
    "VLLM_API_BASE", "http://10.0.0.200:8804/v1"
)
os.environ["LITELLM_PROVIDER_API_KEY"] = os.environ.get("VLLM_API_KEY", "none")
os.environ["LITELLM_PROVIDER_MODEL_NAME"] = "openai/" + os.environ.get(
    "MODEL_NAME", "Qwen/Qwen3-8B"
)

import parlant.sdk as p  # noqa: E402 -- the SDK reads environment settings at import time.

from recruitment_demo_data import RecruitmentData, SessionProfiles  # noqa: E402
from recruitment_demo_handoff import AutoHandoff  # noqa: E402
from recruitment_demo_hr import DemoHR  # noqa: E402
from recruitment_demo_store import DataSourceError, JsonStore  # noqa: E402

AGENT_ID = "cats_worker_v1"
PROFILE_FIELDS = ("full_name", "phone", "job_id")
CONFIG_DIR = Path(
    os.environ.get("CATS_DEMO_DATA_DIR", str(Path(__file__).parent / "data" / "recruitment-demo"))
)
JSON_STORE = JsonStore(CONFIG_DIR, RUNTIME_DIR / "mock-db")
DATA = RecruitmentData(JSON_STORE, AGENT_ID)
PROFILES = SessionProfiles(DATA)
DATA_BY_AGENT = {
    agent_id: DATA if agent_id == AGENT_ID else RecruitmentData(JSON_STORE, agent_id)
    for agent_id in JSON_STORE.read("agents")
}
HR = DemoHR(AGENT_ID, PROFILES, data=DATA, data_by_agent=DATA_BY_AGENT)


def data_for_agent(agent_id: str) -> RecruitmentData:
    if agent_id == AGENT_ID:
        return DATA
    if agent_id not in DATA_BY_AGENT:
        raise PermissionError("Tool is restricted to configured recruitment demo agents")
    return DATA_BY_AGENT[agent_id]


def check_agent(context: p.ToolContext) -> RecruitmentData:
    # Identity is supplied by Parlant, never extracted from the candidate's message.
    return data_for_agent(context.agent_id)


AUTO_HANDOFF = AutoHandoff(HR, data_for_agent)


class ProfilePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    full_name: str | None = Field(None, min_length=2, max_length=150)
    phone: str | None = Field(None, min_length=8, max_length=20)
    job_id: str | None = Field(None, min_length=1, max_length=64)

    @field_validator("full_name", "job_id", mode="before")
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value):
        if value is None:
            return None
        return DATA.validate("phone", value)


def normalize(value: str) -> str:
    return "".join(
        (
            c
            for c in unicodedata.normalize("NFD", value.lower().replace("đ", "d"))
            if unicodedata.category(c) != "Mn"
        )
    )


def supplied_phone_numbers(message: str) -> set[str]:
    parts = re.split("(\\+?[0-9]{8,})", message)
    numbers = {
        re.sub("[\\s.()-]", "", match.group())
        for part in parts
        for match in re.finditer("\\+?[0-9][0-9\\s.()-]{6,}[0-9]", part)
    }
    return {number for number in numbers if re.fullmatch("\\+?[0-9]{8,15}", number)}


@p.tool
@AUTO_HANDOFF.guard_lookup
async def job_list(context: p.ToolContext, query: str = "") -> p.ToolResult:
    """List permitted active jobs; query may be a location or job title, empty lists all."""
    data = check_agent(context)
    print("[tool] job_list", flush=True)
    return p.ToolResult(
        [
            {key: job[key] for key in ("id", "title", "location", "salary")}
            for job in data.jobs(query)
        ]
    )


@p.tool
@AUTO_HANDOFF.guard_lookup
async def search_jd_info(context: p.ToolContext, job_id: str) -> p.ToolResult:
    """Read salary, shifts and JD for a permitted job ID such as CN001 or IT001."""
    data = check_agent(context)
    print("[tool] search_jd_info", flush=True)
    if job_id not in data.job_ids:
        return p.ToolResult(
            {
                "found": False,
                "outside_scope": True,
                "message": "Mã vị trí nằm ngoài phạm vi trợ lý đang chọn. Hướng dẫn ứng viên chọn trợ lý tuyển dụng phù hợp tại /chat; không chuyển HR chỉ vì khác phạm vi.",
            }
        )
    try:
        job = data.job(job_id)
    except ValueError:
        return p.ToolResult(
            {
                "found": False,
                "message": "Vị trí không tồn tại hoặc đã ngừng tuyển. Thông báo trạng thái và gợi ý vị trí đang mở; không chuyển HR chỉ vì vị trí đã đóng.",
            }
        )
    return p.ToolResult(
        {
            "found": True,
            **{
                key: job[key]
                for key in (
                    "id",
                    "company_id",
                    "title",
                    "location",
                    "salary",
                    "jd",
                    "jd_summary",
                    "shift",
                )
            },
        }
    )


@p.tool
@AUTO_HANDOFF.guard_lookup
async def search_knowledge(context: p.ToolContext, query: str) -> p.ToolResult:
    """Search permitted Vietnamese recruitment FAQ and policies."""
    data = check_agent(context)
    print("[tool] search_knowledge", flush=True)
    words = set(normalize(query).split())
    documents = [
        item for key, item in data.store.read("knowledge").items() if key in data.knowledge_ids
    ]
    ranked = sorted(
        documents,
        key=lambda item: len(words & set(normalize(item["title"] + " " + item["content"]).split())),
        reverse=True,
    )
    return p.ToolResult(
        [
            {key: item[key] for key in ("id", "title", "content")}
            for item in ranked[:3]
            if words & set(normalize(item["title"] + " " + item["content"]).split())
        ]
    )


async def populate_profile_template_fields(
    context: p.EngineContext, payload: object, exc: Exception | None
) -> p.EngineHookResult:
    if context.agent.id not in DATA_BY_AGENT:
        return p.EngineHookResult.CALL_NEXT
    data = data_for_agent(context.agent.id)
    # Resolve templates after all tools finish, rather than using a pre-update read.
    try:
        profile = data.profile(context.session.id)
    except (DataSourceError, OSError):
        # Non-profile answers do not require a functioning candidate JSON table.
        return p.EngineHookResult.CALL_NEXT
    labels = {key: rule["label"] for key, rule in data.field_rules.items()}
    labels["job_id"] = "mã vị trí"
    missing = [labels[key] for key in data.missing(profile)]
    # Only this turn's final write determines whether we can confirm a save.
    # A successful write in history must not hide a rejected change now.
    writes = [
        call["result"]["data"]
        for event in getattr(context.state, "tool_events", [])
        for call in event.data.get("tool_calls", [])
        if call["tool_id"].split(":")[-1]
        in {"save_profile", "update_profile", "update_candidate_field"}
    ]
    latest_write = writes[-1] if writes else None
    if latest_write and latest_write.get("saved") is True:
        write_status = "Mình đã lưu thông tin đăng ký quan tâm của bạn."
    elif latest_write and latest_write.get("saved") is False:
        write_status = (
            "Mình chưa lưu được thay đổi vừa gửi. Thông tin đang lưu được hiển thị bên dưới."
        )
    else:
        write_status = "Thông tin đăng ký quan tâm hiện có trong cuộc trò chuyện:"
    next_prompt = (
        f"Bạn cho mình biết {missing[0]} nhé."
        if missing
        else "Hồ sơ đã đủ các trường thông tin bắt buộc."
    )
    if latest_write and latest_write.get("saved") is False:
        next_prompt = (
            "Bạn kiểm tra lại thông tin vừa gửi nhé; thay đổi bị từ chối chưa được áp dụng."
        )
    if not profile:
        next_prompt = "Chưa có hồ sơ đăng ký quan tâm. Bạn có muốn bắt đầu đăng ký không?"
    context.state.additional_canned_response_fields.update(
        {
            "candidate_full_name": profile.get("full_name", "Chưa cung cấp"),
            "candidate_phone": profile.get("phone", "Chưa cung cấp"),
            "candidate_job": profile.get("job_id", "Chưa cung cấp"),
            "candidate_missing": ", ".join(missing)
            if missing
            else "Không còn trường bắt buộc nào bị thiếu",
            "candidate_write_status": write_status,
            "candidate_next_prompt": next_prompt,
        }
    )
    return p.EngineHookResult.CALL_NEXT


async def configure_profile_hooks(hooks: p.EngineHooks) -> p.EngineHooks:
    hooks.on_acknowledging.append(HR.prepare_ai_response)
    hooks.on_preparation_iteration_end.append(
        partial(AUTO_HANDOFF.ensure_company_source, lookup=search_company_info)
    )
    hooks.on_generating_messages.append(AUTO_HANDOFF.before_generation)
    hooks.on_generating_messages.append(HR.guard_ai_response)
    hooks.on_message_generated.append(HR.guard_ai_response)
    hooks.on_generating_messages.append(populate_profile_template_fields)
    return hooks


@p.tool
async def trigger_handoff(
    context: p.ToolContext,
    reason: str = "Ứng viên muốn gặp HR",
    reason_code: str = "candidate_request",
) -> p.ToolResult:
    """Hand over to HR. reason_code: candidate_request or missing_information.

    missing_information requires relevant lookup evidence in the CURRENT turn.
    lookup_error is reserved for backend-detected source errors, never model inference.
    The backend emits the notice; do not send another confirmation or collect a profile.
    """
    check_agent(context)
    reason_code = reason_code or "candidate_request"
    if reason_code not in {"candidate_request", "missing_information"}:
        return p.ToolResult(
            {
                "status": "not_handed_off",
                "message": "Lý do bàn giao không hợp lệ; lỗi tra cứu do backend xác định.",
            }
        )
    if not isinstance(reason, str) or not reason.strip():
        reason = (
            "Nguồn đã tra chưa đủ trả lời câu hỏi hiện tại."
            if reason_code == "missing_information"
            else "Ứng viên muốn gặp HR"
        )
    print("[tool] trigger_handoff", flush=True)
    result = await AUTO_HANDOFF.transfer(
        context.agent_id,
        context.session_id,
        reason_code,
        reason,
        engine=AUTO_HANDOFF.engine_context(context),
    )
    # Never return a mode command: a late tool must not undo an HR resume.
    return p.ToolResult(result)


@p.tool
@AUTO_HANDOFF.guard_lookup
async def get_candidate_profile(context: p.ToolContext, job_id: str = "") -> p.ToolResult:
    """Read the current conversation's candidate profile."""
    data = check_agent(context)
    print("[tool] get_candidate_profile", flush=True)
    try:
        profile = data.profile(context.session_id, job_id)
    except ValueError as exc:
        return p.ToolResult({"exists": False, "error": str(exc)})
    return p.ToolResult(
        {
            "exists": bool(profile),
            **profile,
            "missing_fields": data.missing(profile),
        }
    )


@p.tool
@AUTO_HANDOFF.guard_lookup
async def missing_profile_fields(context: p.ToolContext) -> p.ToolResult:
    """List missing profile fields: full_name, phone, job_id."""
    data = check_agent(context)
    print("[tool] missing_profile_fields", flush=True)
    profile = data.profile(context.session_id)
    return p.ToolResult(data.missing(profile))


@p.tool
async def save_profile(
    context: p.ToolContext, full_name: str = "", phone: str = "", job_id: str = ""
) -> p.ToolResult:
    """Create or patch a registration with any known subset of the optional fields.

    Save a chosen job ID or a name even when the phone number is not known yet.
    Omit unknown fields; never wait for a complete profile. Existing fields are
    preserved. The result reports the saved profile and remaining missing_fields.

    Never join a phone number with an adjacent identity number. For example,
    'Nguyễn An 0901234567 0123456789012' means full_name='Nguyễn An',
    phone='0901234567'; omit the identity number and unknown values.
    """
    data = check_agent(context)
    print("[tool] save_profile", flush=True)
    try:
        patch = ProfilePatch(
            **{
                key: value
                for key, value in {
                    "full_name": full_name,
                    "phone": phone,
                    "job_id": job_id,
                }.items()
                if value
            }
        )
    except ValidationError as exc:
        return p.ToolResult(
            {
                "saved": False,
                "invalid_fields": sorted({str(error["loc"][0]) for error in exc.errors()}),
                "error": "Thông tin hồ sơ chưa hợp lệ. Trích xuất lại đúng nguyên văn họ tên và "
                "một số điện thoại từ tin nhắn; không gộp số điện thoại với CMND/CCCD. "
                "Chỉ hỏi lại ứng viên nếu không xác định được thông tin hợp lệ.",
            }
        )
    values = patch.model_dump(exclude_none=True)
    if not values:
        return p.ToolResult({"saved": False, "error": "Không có thông tin để lưu."})
    if values.get("job_id"):
        try:
            data.job(values["job_id"])
        except ValueError:
            return p.ToolResult(
                {"saved": False, "error": "Vị trí không hợp lệ hoặc ngoài phạm vi."}
            )

    # Read candidate messages directly from Parlant; the model cannot supply this history.
    interaction = p.ToolContextAccessor(context).current_interaction
    texts = [
        unicodedata.normalize("NFC", " ".join(message.content.split()))
        for message in reversed(interaction.messages)
        if message.source == p.EventSource.CUSTOMER
    ]
    if values.get("full_name"):
        name = unicodedata.normalize("NFC", values["full_name"])
        pattern = re.compile(r"(?<!\w)" + re.escape(name) + r"(?!\w)", re.IGNORECASE)
        match = next((found for message in texts if (found := pattern.search(message))), None)
        if not match:
            return p.ToolResult(
                {
                    "saved": False,
                    "retryable": True,
                    "rejected_fields": ["full_name"],
                    "error": "Họ tên không khớp nguyên văn tin nhắn ứng viên. "
                    "Hãy sao chép đúng họ tên, giữ nguyên dấu; không tự sửa tên.",
                    "candidate_message": texts[0] if texts else "",
                }
            )
        values["full_name"] = match.group()
    if values.get("phone"):
        phones = {number for message in texts for number in supplied_phone_numbers(message)}
        if values["phone"] not in phones:
            return p.ToolResult(
                {
                    "saved": False,
                    "retryable": True,
                    "rejected_fields": ["phone"],
                    "error": "Số điện thoại không khớp tin nhắn ứng viên; không tự suy đoán.",
                    "candidate_message": texts[0] if texts else "",
                }
            )
    return p.ToolResult(data.write_profile(context.session_id, values))


@p.tool
async def update_profile(
    context: p.ToolContext, full_name: str = "", phone: str = "", job_id: str = ""
) -> p.ToolResult:
    """Update an existing session profile; never create a new registration."""
    data = check_agent(context)
    if not data.profile(context.session_id):
        return p.ToolResult(
            {
                "saved": False,
                "error": "Chưa có hồ sơ đã lưu để cập nhật. Cần ứng viên yêu cầu đăng ký trước.",
            }
        )
    return await save_profile(context, full_name=full_name, phone=phone, job_id=job_id)


@p.tool
@AUTO_HANDOFF.guard_lookup
async def search_company_info(context: p.ToolContext, job_id: str) -> p.ToolResult:
    """Read employer NAME and BENEFITS for an allowed job: computers/equipment, meals, housing if stated.

    Use for employer benefits and provided equipment questions. JD alone does not
    contain all company benefits. Never infer a particular laptop model.
    """
    data = check_agent(context)
    try:
        return p.ToolResult({"found": True, **data.company(job_id)})
    except ValueError as exc:
        return p.ToolResult({"found": False, "error": str(exc)})


@p.tool
@AUTO_HANDOFF.guard_lookup
async def recommend_jobs(
    context: p.ToolContext, location: str = "", shift: str = "", minimum_salary: float = 0
) -> p.ToolResult:
    """Recommend at most five active allowed jobs. shift: day, rotating, any, or unknown ''."""
    data = check_agent(context)
    try:
        jobs = data.recommend(location=location, shift=shift, minimum_salary=minimum_salary)
        return p.ToolResult(
            [
                {key: row[key] for key in ("id", "title", "location", "salary", "shift")}
                for row in jobs
            ]
        )
    except ValueError as exc:
        return p.ToolResult({"error": str(exc)})


@p.tool
async def validate_field(context: p.ToolContext, field: str, value: str) -> p.ToolResult:
    """Validate one configured field without saving; phone must have ten digits starting with 0."""
    data = check_agent(context)
    try:
        return p.ToolResult({"valid": True, "field": field, "value": data.validate(field, value)})
    except (ValueError, TypeError) as exc:
        return p.ToolResult({"valid": False, "field": field, "error": str(exc)})


def candidate_supplied(context, field, value):
    texts = [
        message.content
        for message in p.ToolContextAccessor(context).current_interaction.messages
        if message.source == p.EventSource.CUSTOMER
    ]
    if field == "preferred_shift":
        aliases = {
            "day": ["ca ngày", "ban ngày", "day"],
            "rotating": ["xoay ca", "luân ca", "rotating"],
            "any": ["bất kỳ ca", "ca nào cũng", "any"],
        }
        return any(
            normalize(alias) in normalize(text) for text in texts for alias in aliases[value]
        )
    if field == "experience_years":
        return any(
            re.search(r"(?<![\d.])" + re.escape(str(value)) + r"(?![\d.])", text) for text in texts
        )
    return any(normalize(str(value)) in normalize(text) for text in texts)


@p.tool
async def update_candidate_field(
    context: p.ToolContext, field: str, value: str, job_id: str = ""
) -> p.ToolResult:
    """Validate and save one candidate-supplied field for this session/job.

    Allowed: full_name, phone, job_id, email, experience_years, available_date
    (YYYY-MM-DD), preferred_location, preferred_shift (day/rotating/any), skills.
    Only collect optional fields if the candidate volunteers them or asks for a
    demo evaluation. Never infer experience, skills, health or personal traits.
    A new job creates a separate application, preserving previous applications.
    """
    data = check_agent(context)
    try:
        clean = data.validate(field, value)
        if job_id:
            data.job(job_id)
    except (ValueError, TypeError) as exc:
        return p.ToolResult({"saved": False, "invalid_fields": [field], "error": str(exc)})
    if field in PROFILE_FIELDS:
        patch = {field: clean}
        if job_id and field != "job_id":
            patch["job_id"] = job_id
        result = await save_profile(context, **patch)
        return complete_profile_write(context, result)
    if not candidate_supplied(context, field, clean):
        return p.ToolResult(
            {
                "saved": False,
                "rejected_fields": [field],
                "error": "Giá trị chưa được ứng viên cung cấp rõ ràng; không tự suy đoán.",
            }
        )
    patch = {field: clean, **({"job_id": job_id} if job_id else {})}
    return complete_profile_write(
        context, p.ToolResult(data.write_profile(context.session_id, patch))
    )


def complete_profile_write(context, result):
    data = check_agent(context)
    if result.data.get("saved") and not result.data["missing_fields"]:
        # The write is committed before mock integration. Integration failure must
        # never turn a saved profile into an apparently failed write.
        try:
            assessment = data.evaluate(context.session_id, result.data["profile"]["job_id"])
            return p.ToolResult(
                {
                    **result.data,
                    "evaluation_id": assessment["evaluation_id"],
                    "crm_sync": data.sync(context.session_id, result.data["profile"]["job_id"]),
                }
            )
        except (OSError, ValueError, RuntimeError) as exc:
            return p.ToolResult({**result.data, "crm_sync": {"synced": False, "error": str(exc)}})
    return result


@p.tool
async def save_candidate_note(context: p.ToolContext, note: str) -> p.ToolResult:
    """Save an HR-only factual note. Never invent personality or hiring conclusions."""
    data = check_agent(context)
    try:
        row = data.add_note(context.session_id, note)
        return p.ToolResult({"saved": True, "note_id": row["id"], "visibility": "hr_only"})
    except ValueError as exc:
        return p.ToolResult({"saved": False, "error": str(exc)})


@p.tool
@AUTO_HANDOFF.guard_lookup
async def check_goal_completion(context: p.ToolContext, job_id: str = "") -> p.ToolResult:
    """Check the shared candidate requirements; zero experience is a valid supplied value."""
    data = check_agent(context)
    try:
        missing = data.missing(data.profile(context.session_id, job_id))
        return p.ToolResult({"completed": not missing, "hard_missing": missing})
    except ValueError as exc:
        return p.ToolResult({"completed": False, "error": str(exc)})


@p.tool
async def evaluate_candidate(context: p.ToolContext, job_id: str = "") -> p.ToolResult:
    """Produce a five-criterion SIMULATION for HR, cache by profile/job/policy snapshot and sync mock CRM.

    Unknown criteria yield HOLD, never infer missing facts. This is not a hiring
    decision and must not be presented as acceptance/rejection to the candidate.
    """
    data = check_agent(context)
    try:
        result = data.evaluate(context.session_id, job_id)
        return p.ToolResult({**result, "crm_sync": data.sync(context.session_id, job_id)})
    except ValueError as exc:
        return p.ToolResult({"evaluated": False, "error": str(exc)})


@p.tool
async def sync_applicant_info(context: p.ToolContext, job_id: str = "") -> p.ToolResult:
    """Sync this session's application and current assessment into LOCAL MOCK CRM only."""
    data = check_agent(context)
    try:
        return p.ToolResult(data.sync(context.session_id, job_id))
    except ValueError as exc:
        return p.ToolResult({"synced": False, "error": str(exc), "is_mock": True})


# Old Python entry points remain usable for tests/scripts. Native tools use registry keys.
list_jobs = job_list
get_job = search_jd_info
get_profile = get_candidate_profile
request_handoff = trigger_handoff
TOOL_REGISTRY = {
    "search_jd_info": search_jd_info,
    "search_company_info": search_company_info,
    "job_list": job_list,
    "recommend_jobs": recommend_jobs,
    "get_candidate_profile": get_candidate_profile,
    "update_candidate_field": update_candidate_field,
    "validate_field": validate_field,
    "save_candidate_note": save_candidate_note,
    "check_goal_completion": check_goal_completion,
    "evaluate_candidate": evaluate_candidate,
    "sync_applicant_info": sync_applicant_info,
    "trigger_handoff": trigger_handoff,
    "resume_agent": HR.resume,
}


async def add_domain_glossary(agent: p.Agent, agent_id: str = AGENT_ID) -> None:
    prefix = agent_id.replace("_", "-")
    await agent.create_term(
        id=f"{prefix}-term-attendance",
        name="Phụ cấp chuyên cần",
        description="Khoản phụ cấp khi đi làm đủ ngày công theo quy định; số tiền phải lấy từ JD.",
        synonyms=["thưởng chuyên cần", "tiền đi làm đủ"],
    )
    await agent.create_term(
        id=f"{prefix}-term-shift",
        name="Xoay ca",
        description="Luân phiên giữa các ca theo lịch của từng vị trí; không mặc định là làm ca đêm.",
        synonyms=["luân ca", "đổi ca"],
    )


async def add_guidelines(agent: p.Agent, agent_id: str = AGENT_ID) -> p.CannedResponseId:
    prefix = agent_id.replace("_", "-")
    name = data_for_agent(agent_id).agent["name"]
    await agent.create_guideline(
        id=f"{prefix}-guideline-human-handoff",
        condition=(
            "Tin nhắn mới nhất của ứng viên yêu cầu nói chuyện với người thật, nhân viên "
            "hoặc chuyên viên tuyển dụng/HR thay cho trợ lý. Không áp dụng khi chỉ hỏi "
            "nghề HR là gì hoặc nhắc lại yêu cầu đã được HR xử lý."
        ),
        action=(
            "Gọi trigger_handoff với reason_code=candidate_request và lý do ngắn gọn. Chỉ "
            "xác nhận đã bàn giao khi tool báo waiting_for_hr. Nếu tool báo handoff_failed, "
            "nói chưa chuyển được; không nói đã chuyển. Khi thành công, tool đã gửi "
            "thông báo chờ HR và dừng AI; không tiếp tục hỏi đăng ký hoặc thu thập hồ sơ."
        ),
        tools=[trigger_handoff],
        track=False,
    )
    profile_summary = await agent.create_canned_response(
        template=(
            "Hồ sơ bạn đã cung cấp:\n- Họ tên: {{candidate_full_name}}\n- Số điện thoại: "
            "{{candidate_phone}}\n- Vị trí: {{candidate_job}}\nThông tin còn thiếu: "
            "{{candidate_missing}}.\nĐây là đăng ký quan tâm, chưa phải kết quả tuyển dụng."
        ),
        field_dependencies=[
            "candidate_full_name",
            "candidate_phone",
            "candidate_job",
            "candidate_missing",
        ],
    )
    profile_confirmation = await agent.create_canned_response(
        template=(
            "{{candidate_write_status}}\n- Họ tên: {{candidate_full_name}}\n"
            "- Số điện thoại: {{candidate_phone}}\n- Vị trí: {{candidate_job}}\n"
            "{{candidate_next_prompt}}\nĐây là đăng ký quan tâm, chưa phải kết quả tuyển dụng."
        ),
        field_dependencies=[
            "candidate_write_status",
            "candidate_full_name",
            "candidate_phone",
            "candidate_job",
            "candidate_next_prompt",
        ],
    )
    greeting = await agent.create_canned_response(
        template=f"Chào bạn! Mình là {name} của CATS.",
    )
    unknown = await agent.create_canned_response(
        template="Nội dung này nằm ngoài phạm vi tư vấn của trợ lý hiện tại. Bạn có thể chọn trợ lý tuyển dụng phù hợp để được hỗ trợ.",
    )
    await agent.create_guideline(
        id=f"{prefix}-guideline-glossary",
        condition=(
            "Yêu cầu hiện tại của ứng viên là giải thích nghĩa một thuật ngữ tuyển dụng, "
            "không phải hỏi mức tiền, lịch ca hoặc điều kiện thực tế của một vị trí cụ thể"
        ),
        action=(
            "Giải thích ngắn gọn bằng định nghĩa trong glossary được cung cấp. Glossary là "
            "nguồn kiến thức đã xác minh, không cần tìm FAQ để định nghĩa thuật ngữ. Không "
            "nói thiếu thông tin nếu glossary đã định nghĩa. Không dùng định nghĩa chung "
            "để suy ra mức tiền hoặc lịch ca của một vị trí."
        ),
        track=False,
    )
    await agent.create_guideline(
        id=f"{prefix}-guideline-clarify-application",
        condition=(
            "Tin nhắn hiện tại có lời đề nghị đăng ký/ứng tuyển nhưng ý định bắt đầu "
            "nộp hồ sơ còn mơ hồ, hoặc ứng viên trả lời mơ hồ một câu hỏi đăng ký đã được hỏi. "
            "Không áp dụng cho câu hỏi chỉ tìm hiểu JD, lương, thiết bị, phúc lợi, công ty "
            "hay chính sách; hỏi 'có cấp MacBook không' không phải ý định đăng ký."
        ),
        action=(
            "Hỏi một câu ngắn để làm rõ ý định, gắn với vị trí đang trao đổi. "
            "Ví dụ: 'Bạn muốn đăng ký ứng tuyển CN002 hay tìm hiểu thêm trước?'. "
            "Chưa yêu cầu họ tên hoặc số điện thoại và chưa lưu hồ sơ. "
            "Không hỏi xác nhận đăng ký chỉ vì ứng viên hỏi JD, lương, ca làm, "
            "thông tin công ty hoặc muốn gặp nhân viên. "
            "Nếu ứng viên đã yêu cầu đăng ký rõ ràng thì không hỏi lại."
        ),
        track=False,
    )
    await agent.create_guideline(
        id=f"{prefix}-guideline-save",
        track=False,
        composition_mode=p.CompositionMode.STRICT,
        condition=(
            "Ứng viên đang sửa hoặc bổ sung thông tin cho hồ sơ đăng ký của mình, kể cả "
            "bổ sung trường còn thiếu sau khi đã lưu một phần hồ sơ. Chỉ nhắc tới tên, "
            "số điện thoại hoặc mã công việc khi tìm hiểu việc làm không phải cập nhật hồ sơ"
        ),
        action=(
            "Gọi get_candidate_profile để đọc hồ sơ trước. Nếu exists=true, gọi update_candidate_field chỉ với "
            "từng trường ứng viên yêu cầu sửa bằng field/value và job_id đang chọn; giữ nguyên trường khác. Sao chép đúng "
            "họ tên có dấu và một số điện thoại, không ghép với dãy số giấy tờ. Chỉ xác "
            "nhận cập nhật theo kết quả tool; không coi hồ sơ từng phần là đã đủ. Nếu "
            "exists=false, nói rõ chưa có hồ sơ để sửa và hỏi ứng viên có muốn đăng ký "
            "không; chưa tạo hồ sơ. Việc lưu thông tin đăng ký ban đầu thuộc journey."
        ),
        tools=[get_candidate_profile, update_candidate_field, validate_field],
        canned_responses=[profile_confirmation],
    )
    await agent.create_guideline(
        id=f"{prefix}-guideline-profile-collection",
        track=False,
        condition=(
            "Đang xử lý dữ liệu hồ sơ ứng tuyển hoặc ứng viên hỏi cần cung cấp thông tin "
            "gì để đăng ký"
        ),
        action=(
            "Hồ sơ bắt buộc chỉ gồm họ tên, số điện thoại và mã vị trí. Có thể lưu email, kinh nghiệm, ngày bắt đầu, khu vực, ca làm và kỹ năng nếu ứng viên tự cung cấp; không bắt buộc các trường này chỉ để đăng ký. Không "
            "yêu cầu số CMND, CCCD, ảnh giấy tờ tùy thân hoặc thông tin ngân hàng; không "
            "nhắc lại các giá trị nhạy cảm ứng viên đã gửi. Đây là giới hạn dữ liệu, "
            "không phải yêu cầu bắt đầu thu thập hồ sơ. Chỉ bước thu thập trong journey "
            "đăng ký mới chủ động hỏi các trường còn thiếu. Khi ứng viên hỏi thủ tục, "
            "chỉ giải thích yêu cầu; không yêu cầu họ gửi thông tin ngay. Không cần lặp "
            "lại lưu ý giấy tờ ở mọi lượt. Không hứa tự gọi lại hoặc xác nhận trúng tuyển."
            " Chỉ nói đã lưu hoặc đủ hồ sơ theo kết quả tool mới nhất, không suy ra từ "
            "thông tin ứng viên vừa gửi. Không hứa sẽ liên hệ hoặc xét duyệt khi chưa có "
            "nguồn xác nhận việc đó."
            " Khi thu thập hồ sơ, chỉ hỏi một trường còn thiếu ở mỗi lượt. Mã vị trí "
            "ứng viên đã chọn rõ ràng, kể cả trong trao đổi với HR, là thông tin đã biết; "
            "không yêu cầu ứng viên nhập lại mã đó. Không chào lại ở mỗi lượt."
        ),
    )
    await agent.create_guideline(
        id=f"{prefix}-guideline-read-profile",
        track=False,
        composition_mode=p.CompositionMode.STRICT,
        condition=(
            "Ứng viên đang yêu cầu xem hồ sơ đã lưu hoặc hỏi hồ sơ đó còn thiếu trường "
            "nào; câu hỏi thiếu thông tin chỉ áp dụng khi ngữ cảnh đang nói về hồ sơ"
        ),
        action=(
            "Gọi get_candidate_profile và check_goal_completion. Dùng mẫu hồ sơ với các trường do "
            "tool cung cấp; giữ nguyên văn họ tên, số điện thoại và mã vị trí, không viết "
            "lại hoặc sửa dấu. Nếu chưa có hồ sơ, nói rõ chưa có. Chỉ báo trạng thái, "
            "không tự bắt đầu đăng ký hoặc yêu cầu ứng viên bổ sung ngay."
        ),
        tools=[get_candidate_profile, check_goal_completion],
        canned_responses=[profile_summary],
    )
    await agent.create_guideline(
        id=f"{prefix}-guideline-greet",
        track=False,
        condition="Ứng viên chào hỏi và chưa hỏi nội dung khác",
        action=(
            "Chào ngắn gọn. Chỉ hỏi khu vực muốn tìm việc nếu chưa biết; nếu đã biết thì "
            "hỏi ứng viên cần hỗ trợ nội dung gì."
        ),
        canned_responses=[greeting],
    )
    await agent.create_guideline(
        id=f"{prefix}-guideline-jobs",
        track=False,
        condition=(
            "Yêu cầu hiện tại của ứng viên là tìm hoặc liệt kê các vị trí đang tuyển, "
            "hoặc đổi tiêu chí tìm kiếm; không chỉ vì trước đó họ từng hỏi tìm việc"
        ),
        action=(
            "Gọi job_list với query giữ nguyên địa điểm hoặc tên việc ứng viên cung cấp, "
            "không tự dịch hay đổi cách viết. Chỉ giới thiệu công việc trong kết quả tool, kèm mã vị trí. "
            "Nếu danh sách rỗng, nói chưa có việc phù hợp và gợi ý đổi tiêu chí, không "
            "tự chuyển HR. Đề nghị ứng viên chọn vị trí muốn tìm hiểu nếu cần. Chưa yêu cầu tên hoặc "
            "số điện thoại và chưa coi việc tham khảo là chọn ứng tuyển."
        ),
        tools=[job_list],
    )
    await agent.create_guideline(
        id=f"{prefix}-guideline-jd",
        track=False,
        condition="Yêu cầu hiện tại của ứng viên là hỏi lương, lịch ca, yêu cầu hoặc chi tiết thực tế của vị trí",
        action=(
            "Gọi search_jd_info với mã công việc phù hợp. Nếu chưa rõ mã, hỏi lại hoặc liệt kê "
            "việc bằng job_list. Trả lời đúng JD; không dùng dữ liệu đoán từ tên công việc. "
            "Nếu JD chưa trả lời đủ, đối chiếu search_company_info hoặc search_knowledge khi phù hợp. "
            "Còn thiếu thông tin trong phạm vi thì gọi trigger_handoff với "
            "reason_code=missing_information; không chỉ hứa sẽ chuyển. Chỉ xác nhận bàn giao "
            "khi tool báo waiting_for_hr. "
            "Phân biệt vị trí đang được tham khảo với vị trí ứng viên đã chọn để ứng tuyển; "
            "không yêu cầu hồ sơ chỉ vì ứng viên hỏi chi tiết."
        ),
        tools=[search_jd_info, job_list, search_company_info, search_knowledge, trigger_handoff],
    )
    await agent.create_guideline(
        id=f"{prefix}-guideline-knowledge",
        track=False,
        condition="Ứng viên hỏi phí, chính sách hoặc thủ tục ứng tuyển",
        action=(
            "Với chính sách của một job, ưu tiên search_jd_info/search_company_info rồi "
            "tra search_knowledge nếu cần. FAQ có từ khóa trùng chưa chắc trả lời đúng câu hỏi. "
            "Chỉ dùng phần được tài liệu hoặc HR trong chính phiên này xác nhận. Còn thiếu "
            "thông tin trong phạm vi thì gọi trigger_handoff với reason_code=missing_information, "
            "không chỉ nói chưa có thông tin hoặc hứa sẽ chuyển. Chỉ xác nhận bàn giao "
            "khi tool báo waiting_for_hr. "
            "Hỏi phí, chính sách hoặc thủ "
            "tục là tìm hiểu thông tin, chưa phải đồng ý đăng ký; chưa yêu cầu gửi hồ sơ."
        ),
        tools=[search_knowledge, search_jd_info, search_company_info, trigger_handoff],
    )
    scope = await agent.create_guideline(
        id=f"{prefix}-guideline-scope",
        track=False,
        condition=(
            "Câu hỏi hiện tại nằm ngoài tuyển dụng hoặc yêu cầu job/dữ liệu ngoài quyền "
            "của agent đang chọn. Mọi câu hỏi về điều kiện làm việc, chính sách, phúc lợi "
            "hay thiết bị được cấp cho job agent được phép tư vấn đều thuộc phạm vi tuyển dụng, "
            "kể cả hỏi có cấp MacBook hoặc hỗ trợ chỗ ở. Chưa có câu trả lời không phải ngoài quyền."
        ),
        action=(
            "Không suy đoán hay tiết lộ dữ liệu không được cấp. Nói rõ giới hạn; nếu hỏi "
            "job của agent khác thì hướng dẫn chọn agent phù hợp, không tự chuyển HR. "
            "Không có job phù hợp hoặc job đã đóng là kết quả tra cứu hợp lệ: trả lời trạng thái "
            "và gợi ý việc khác, không bàn giao chỉ vì tool rỗng."
        ),
        canned_responses=[unknown],
    )
    await agent.create_guideline(
        id=f"{prefix}-guideline-company",
        condition="Ứng viên hỏi thông tin doanh nghiệp, nhà tuyển dụng, phúc lợi, thiết bị được cấp hoặc hỗ trợ của công ty cho một vị trí",
        action="Gọi search_company_info theo job_id đang trao đổi; chỉ dùng thông tin công ty được tool trả về. Nếu chưa đủ, đối chiếu JD/FAQ phù hợp. Chưa rõ job thì hỏi lại. Nếu vẫn thiếu thông tin trong phạm vi, gọi trigger_handoff với reason_code=missing_information; chỉ xác nhận bàn giao khi tool báo waiting_for_hr, không chỉ hứa sẽ chuyển. Nếu nguồn chỉ nói cấp máy tính nhưng ứng viên hỏi có cấp MacBook không, đó là THIẾU THÔNG TIN và phải gọi trigger_handoff(reason_code=missing_information), kể cả họ chỉ hỏi tham khảo. Không chỉ trả lời không thể suy ra rồi kết thúc.",
        tools=[search_company_info, search_jd_info, search_knowledge, trigger_handoff],
        track=False,
    )
    await agent.create_guideline(
        id=f"{prefix}-guideline-recommend",
        condition="Ứng viên nhờ gợi ý công việc theo khu vực, ca làm hoặc mức lương mong muốn",
        action="Gọi recommend_jobs, tối đa 5 vị trí. Không suy đoán ca hoặc mức lương chưa được cung cấp.",
        tools=[recommend_jobs],
        track=False,
    )
    await agent.create_guideline(
        id=f"{prefix}-guideline-note",
        condition="Ứng viên yêu cầu ghi chú nguyện vọng hoặc thông tin bổ sung cho HR",
        action="Gọi save_candidate_note với nội dung thực tế ứng viên đã cung cấp; không thêm nhận xét tính cách hay kết luận tuyển dụng.",
        tools=[save_candidate_note],
        track=False,
    )
    await agent.create_guideline(
        id=f"{prefix}-guideline-assessment",
        condition="Ứng viên yêu cầu đánh giá mô phỏng hồ sơ hoặc đồng bộ hồ sơ đã đăng ký sang CRM giả lập",
        action="Gọi check_goal_completion trước; nếu chưa đủ chỉ hỏi trường còn thiếu. Khi đủ, gọi evaluate_candidate hoặc sync_applicant_info theo yêu cầu. Kết quả chỉ là mô phỏng nội bộ cho HR xem xét; không thông báo trúng tuyển, bị loại, hứa xét duyệt hay hứa HR liên hệ.",
        tools=[check_goal_completion, evaluate_candidate, sync_applicant_info],
        track=False,
    )
    evidence = await agent.create_guideline(
        id=f"{prefix}-guideline-lookup-evidence",
        condition="Đã có bằng chứng tra cứu thuộc phạm vi ở lượt hiện tại, không chỉ là không có job phù hợp hoặc hồ sơ chưa tồn tại.",
        matcher=AUTO_HANDOFF.evidence_ready,
        track=False,
    )
    await evidence.reevaluate_after(search_jd_info, search_company_info, search_knowledge)
    missing_information = await agent.create_guideline(
        id=f"{prefix}-guideline-missing-information",
        dependencies=[evidence],
        track=False,
        condition=(
            "The latest user message asks a recruitment question and at least one EXACT "
            "detail being asked is NOT explicitly confirmed by the current tool results "
            "or an HR reply in this session. A related/general fact is NOT an answer to "
            "a specific detail. For example, 'computer provided' does NOT answer 'MacBook "
            "provided?': unless a source explicitly confirms or denies MacBook, this "
            "condition is TRUE. The user does NOT need to demand that detail as a mandatory "
            "requirement; simply asking is enough. Do not decide an asked detail is unimportant."
        ),
        action=(
            "Gọi trigger_handoff với reason_code=missing_information và reason ghi rõ ý "
            "chưa xác nhận được, không yêu cầu ứng viên chủ động xin gặp HR. Chỉ bàn giao "
            "sau khi tra nguồn đúng. Thông tin chung không thay cho chi tiết cụ thể ứng viên "
            "hỏi; không cần ứng viên đặt điều kiện bắt buộc mới bàn giao. Không chỉ nói chưa "
            "có thông tin hoặc không thể suy ra, không đoán câu trả lời "
            "và không thu thập tiếp hồ sơ. Khi tool báo waiting_for_hr, backend đã gửi thông "
            "báo và dừng AI, không gửi thêm lời xác nhận. Nếu handoff_failed thì nói chưa "
            "chuyển được. Sau khi HR trả về AI, dùng câu trả lời HR trong phiên nếu đã rõ; "
            "không tự ghi lời HR thành FAQ chung."
        ),
        tools=[trigger_handoff],
    )
    # Relational precedence only affects scope; numerical priority would remove
    # the evidence dependency and all lower-priority lookup guidelines too.
    await missing_information.prioritize_over(scope)
    # Parlant only revisits tool-dependent conditions after explicitly linked tools.
    await missing_information.reevaluate_after(
        search_jd_info, search_company_info, search_knowledge
    )
    await agent.create_guideline(
        id=f"{prefix}-guideline-lookup-error",
        track=False,
        condition="Tool trả lookup_failed=true hoặc handoff_status=handoff_failed ở lượt hiện tại",
        action=(
            "Đây là lỗi tra cứu, không phải không có job hay không có hồ sơ. Không thử lại "
            "tool tra cứu trong lượt này. Backend đã thực hiện bàn giao; không tự gán "
            "lookup_error khi tool chưa báo lỗi. Nếu handoff_status=handoff_failed, chỉ nói "
            "chưa chuyển được sang HR, vui lòng thử lại sau; không tuyên bố đã bàn giao."
        ),
    )
    return profile_confirmation


async def create_application_journey(
    agent: p.Agent, profile_confirmation: p.CannedResponseId, agent_id: str = AGENT_ID
) -> p.Journey:
    prefix = agent_id.replace("_", "-")
    collection_prompt = await agent.create_canned_response(
        template="{{candidate_next_prompt}}",
        field_dependencies=["candidate_next_prompt"],
    )
    new_profile_information = (
        "Có ít nhất một trường hợp lệ ứng viên đã cung cấp hoặc mã vị trí đã chọn "
        "để ứng tuyển chưa được lưu hay khác hồ sơ tool trả về, và ứng viên chưa hủy "
        "đăng ký. Không thử lại dữ liệu tool đã từ chối khi chưa có sửa đổi"
    )
    journey = await agent.create_journey(
        id=f"{prefix}-journey-application",
        title="Đăng ký ứng tuyển",
        description="Đăng ký vị trí ứng viên chọn, lưu hồ sơ từng phần và báo kết quả từ tool.",
        triggers=[
            "Ứng viên đã chọn vị trí để đăng ký ứng tuyển hoặc xác nhận muốn đăng ký vị trí trợ lý vừa nêu."
        ],
    )
    select = await journey.initial_state.transition_to(
        id=f"{prefix}-application-select",
        chat_state=(
            "Xác định vị trí ứng viên muốn đăng ký. Nếu họ chỉ đang tham khảo một vị trí, "
            "hỏi đó có phải vị trí muốn ứng tuyển không. Chỉ hỏi mã nếu chưa xác định được "
            "vị trí qua lựa chọn hoặc xác nhận của ứng viên."
            " Giữ nguyên lựa chọn ứng viên vừa xác nhận với HR trong cùng cuộc trò chuyện."
        ),
    )
    detail = await select.target.transition_to(
        id=f"{prefix}-application-detail",
        tool_state=search_jd_info,
        tool_instruction="Tra cứu JD của vị trí ứng viên chọn.",
        condition="Ứng viên đã chọn hoặc xác nhận rõ vị trí muốn ứng tuyển, không chỉ hỏi thông tin vị trí đó",
    )
    await detail.target.transition_to(
        state=select.target,
        condition="search_jd_info trả về found=false; đề nghị chọn lại một vị trí đang tuyển trong phạm vi",
    )
    save = await detail.target.transition_to(
        id=f"{prefix}-application-save",
        tool_state=update_candidate_field,
        tool_instruction=(
            "Gọi update_candidate_field cho từng trường mới: field là tên trường, value là giá trị, "
            "job_id là vị trí đang đăng ký. Lưu mã vị trí bằng field=job_id trước, rồi lưu "
            "các thông tin ứng viên tự cung cấp. Không tự chuyển dữ liệu hồ sơ từ job cũ. "
            "Giữ mã vị trí "
            "họ đã chọn để ứng tuyển. Sao chép nguyên văn họ tên có dấu và một số điện "
            "thoại; không ghép số điện thoại với số giấy tờ. Bỏ qua trường chưa biết, "
            "giữ nguyên trường đã lưu. Có thể lưu từng phần, không đợi đủ cả họ tên và "
            "số điện thoại; không gọi lại với dữ liệu không thay đổi."
        ),
        condition="search_jd_info trả về found=true cho vị trí ứng viên đã chọn ứng tuyển và ứng viên chưa hủy đăng ký",
    )
    collect = await save.target.transition_to(
        id=f"{prefix}-application-collect",
        chat_state=(
            "Hỏi một trường còn thiếu hoặc cần sửa theo kết quả update_candidate_field mới nhất. "
            "Bước hỏi hoàn thành ngay khi ứng viên cung cấp ít nhất một trường mới hợp "
            "lệ để lưu; không đợi đủ cả hồ sơ. Không hỏi lại dữ liệu đã có và chỉ xác "
            "nhận dữ liệu tool đã lưu. Nếu ứng viên hỏi xen ngang, trả lời câu hỏi rồi "
            "tiếp tục đăng ký khi họ sẵn sàng."
        ),
        condition="Kết quả update_candidate_field mới nhất còn missing_fields hoặc có saved=false",
        composition_mode=p.CompositionMode.STRICT,
        canned_responses=[collection_prompt],
    )
    await collect.target.transition_to(state=save.target, condition=new_profile_information)
    done = await save.target.transition_to(
        id=f"{prefix}-application-done",
        chat_state=(
            "Báo đúng trạng thái hồ sơ từ tool mới nhất. Nếu còn missing_fields, nói rõ "
            "còn thiếu gì và hỏi thông tin đó, không nói đã đủ hồ sơ. Nếu đã đủ, nói đã "
            "ghi nhận đăng ký quan tâm, chưa phải xác nhận trúng tuyển. Không hứa liên "
            "hệ, xét duyệt hoặc thông báo kết quả ngoài dữ liệu được cấp."
        ),
        condition="Kết quả update_candidate_field mới nhất có saved=true và missing_fields rỗng",
        composition_mode=p.CompositionMode.STRICT,
        canned_responses=[profile_confirmation],
    )
    await collect.target.transition_to(
        state=p.END_JOURNEY,
        condition="Ứng viên hủy hoặc yêu cầu dừng đăng ký; giữ nguyên thông tin đã lưu",
    )
    await done.target.transition_to(
        state=p.END_JOURNEY,
        condition="Kết quả tool mới nhất xác nhận hồ sơ đủ họ tên, số điện thoại và mã vị trí",
    )
    await done.target.transition_to(
        state=collect.target,
        condition="Kết quả tool mới nhất vẫn còn trường thiếu hoặc bị từ chối",
    )
    return journey


async def create_demo_agent(server, data: RecruitmentData | None = None):
    data = data if data is not None else DATA
    config = data.agent
    if config["id"] != data.agent_id:
        raise ValueError("Configured agent id does not match the selected demo agent")
    if config["perceived_performance_policy"] != "null":
        raise ValueError("The demo supports perceived_performance_policy='null' only")
    iterations = config["max_engine_iterations"]
    if type(iterations) is not int or iterations < 1:
        raise ValueError("max_engine_iterations must be a positive integer")
    try:
        composition_mode = p.CompositionMode[config["composition_mode"]]
        output_mode = p.OutputMode[config["output_mode"]]
    except KeyError as exc:
        raise ValueError("Invalid agent composition_mode or output_mode") from exc
    return await server.create_agent(
        id=config["id"],
        name=config["name"],
        description=config["description"],
        composition_mode=composition_mode,
        output_mode=output_mode,
        max_engine_iterations=iterations,
        perceived_performance_policy=p.NullPerceivedPerformancePolicy(),
    )


async def main() -> None:
    async with p.Server(
        host="127.0.0.1",
        port=8800,
        tool_service_port=8818,
        nlp_service=p.NLPServices.litellm,
        log_level=p.LogLevel.TRACE,
        session_store="local",
        customer_store="local",
        configure_hooks=configure_profile_hooks,
        initialize_container=HR.initialize,
        configure_api=HR.configure_api,
    ) as server:
        for agent_id, data in DATA_BY_AGENT.items():
            agent = await create_demo_agent(server, data)
            await add_domain_glossary(agent, agent_id)
            profile_confirmation = await add_guidelines(agent, agent_id)
            await create_application_journey(agent, profile_confirmation, agent_id)
        names = ", ".join(data.agent["name"] for data in DATA_BY_AGENT.values())
        print(f"Demo: http://localhost:8800/chat — chọn {names}", flush=True)
        print("HR:   http://localhost:8800/hr — nhận phiên và trả lời ứng viên", flush=True)
    # As in healthcare.py, the SDK starts serving when setup exits this block.


if __name__ == "__main__":
    asyncio.run(main())
