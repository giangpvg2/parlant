"""Recruitment rules and a JSON-only AgentToolClient for the standalone demo."""

import copy
import hashlib
import json
import math
import re
import time
import unicodedata
from collections.abc import MutableMapping
from datetime import date, datetime, timezone
from uuid import NAMESPACE_URL, uuid4, uuid5

from recruitment_demo_store import JsonStore


def now():
    return datetime.now(timezone.utc).isoformat()


def normalized(value):
    return "".join(
        character
        for character in unicodedata.normalize("NFD", str(value).lower().replace("đ", "d"))
        if unicodedata.category(character) != "Mn"
    )


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()


def present(value):
    return value is not None and value != "" and value != []


class MockAgentToolClient:
    """External-platform contract, implemented locally; never makes HTTP requests."""

    def __init__(self, store: JsonStore):
        self.store = store
        self._job_cache = {}

    def get_job_details(self, job_id):
        return self.store.read("jobs").get(job_id)

    def get_company_details(self, company_id):
        return self.store.read("companies").get(company_id)

    def job_list(self, **params):
        allowed = set(params["job_ids"])
        key = (tuple(sorted(allowed)), self.store.path("jobs").stat().st_mtime_ns)
        cached = self._job_cache.get(key)
        if cached and cached[0] > time.monotonic():
            return copy.deepcopy(cached[1])
        rows = [
            row
            for identifier, row in self.store.read("jobs").items()
            if identifier in allowed and row["active"]
        ]
        self._job_cache = {key: (time.monotonic() + 30, rows)}
        return copy.deepcopy(rows)

    def get_contact_info(self, contact_id):
        return self.store.read("crm_contacts").get(contact_id)

    def update_contact_info(self, payload):
        identifier = (
            payload.get("contact_id")
            or "mock-" + uuid5(NAMESPACE_URL, payload["application_id"]).hex
        )

        def upsert(items):
            contact = items.setdefault(
                identifier, {"contact_id": identifier, "is_mock": True, "applications": {}}
            )
            contact.update(payload["collected"])
            contact["applications"][payload["application_id"]] = {
                "application_id": payload["application_id"],
                "job_id": payload["job_id"],
                "profile_snapshot_hash": payload["profile_snapshot_hash"],
                "ai_initial_assessment": payload["ai_initial_assessment"],
                "status": "PENDING_HR_REVIEW",
                "synced_at": now(),
            }
            return contact

        return self.store.update("crm_contacts", upsert)

    def create_private_message(
        self,
        conversation_id,
        msg,
        *,
        agent_id,
        request_key="",
        kind="handoff_message",
        author="system",
        application_id=None,
    ):
        if not msg.strip() or len(msg) > 2000:
            raise ValueError("Ghi chú cần từ 1 đến 2000 ký tự")
        identifier = fingerprint([agent_id, conversation_id, request_key or [kind, msg, author]])

        def append(items):
            row = {
                "id": identifier,
                "agent_id": agent_id,
                "session_id": conversation_id,
                "application_id": application_id,
                "kind": kind,
                "visibility": "hr_only",
                "text": msg.strip(),
                "author": author,
                "created_at": now(),
            }
            existing = items.get(identifier)
            if existing and any(existing[key] != row[key] for key in ("text", "author", "kind")):
                raise ValueError("Mã ghi chú đã được dùng cho nội dung khác")
            return items.setdefault(identifier, row)

        return self.store.update("candidate_notes", append)


class RecruitmentData:
    def __init__(self, store: JsonStore, agent_id: str):
        self.store = store
        self.agent_id = agent_id
        self.client = MockAgentToolClient(store)
        self.agent = store.read("agents")[agent_id]
        self.candidate_schema = store.read("candidate_schema")["default"]
        self.field_rules = self.candidate_schema["field_rules"]
        self.required_fields = tuple(self.candidate_schema["required_fields"])
        if not self.required_fields or len(set(self.required_fields)) != len(self.required_fields):
            raise ValueError("Shared candidate required_fields must be nonempty and unique")
        if not set(self.required_fields) <= {*self.field_rules, "job_id"}:
            raise ValueError("Shared candidate schema requires an unsupported field")
        jobs = store.read("jobs")
        knowledge = store.read("knowledge")
        companies = store.read("companies")
        self.job_ids = {key for key, row in jobs.items() if agent_id in row["agent_ids"]}
        self.knowledge_ids = {key for key, row in knowledge.items() if agent_id in row["agent_ids"]}
        if any(row["company_id"] not in companies for row in jobs.values()):
            raise ValueError("Job references an unknown company")
        criteria = {
            "experience_years",
            "skills",
            "preferred_shift",
            "preferred_location",
            "available_date",
        }
        for job in jobs.values():
            if set(job["evaluation_policy"]["criteria"]) != criteria:
                raise ValueError(
                    "The demo assessment requires the five supported job-related criteria"
                )

    def job(self, job_id, *, active=True):
        if job_id not in self.job_ids:
            raise ValueError("Vị trí ngoài phạm vi agent")
        row = self.client.get_job_details(job_id)
        if not row or (active and not row["active"]):
            raise ValueError("Vị trí không tồn tại hoặc đã ngừng tuyển")
        return row

    def jobs(self, query=""):
        words = set(normalized(query).split())
        return [
            row
            for row in self.client.job_list(job_ids=self.job_ids)
            if not words
            or words
            <= set(
                normalized(" ".join([row["title"], row["location"], *row.get("tags", [])])).split()
            )
        ]

    def company(self, job_id):
        job = self.job(job_id)
        return self.client.get_company_details(job["company_id"])

    def recommend(self, *, location="", shift="", minimum_salary=0):
        if minimum_salary < 0 or not math.isfinite(minimum_salary):
            raise ValueError("Mức lương mong muốn phải là số không âm")
        if shift and shift not in {"day", "rotating", "any"}:
            raise ValueError("Ca làm cần là day, rotating hoặc any")
        matches = []
        for job in self.jobs():
            if location and normalized(location) not in normalized(job["location"]):
                continue
            if shift not in {"", "any", job["shift"]}:
                continue
            # An unknown upper salary is not evidence that the requested salary is available.
            if minimum_salary > (job.get("salary_max") or job["salary_min"]):
                continue
            matches.append(job)
        return sorted(matches, key=lambda row: (-row["salary_min"], row["id"]))[:5]

    def validate(self, field, value):
        if field == "job_id":
            return self.job(str(value).strip())["id"]
        rule = self.field_rules.get(field)
        if not rule:
            raise ValueError("Trường không được phép thu thập")
        if isinstance(value, bool) or value is None:
            raise ValueError("Giá trị không hợp lệ")
        kind = rule["type"]
        if kind == "number":
            number = float(value)
            if not math.isfinite(number) or not rule["minimum"] <= number <= rule["maximum"]:
                raise ValueError("Số năm kinh nghiệm phải nằm trong giới hạn cấu hình")
            return int(number) if number.is_integer() else number
        if not isinstance(value, str):
            raise ValueError("Giá trị phải là chuỗi")
        value = unicodedata.normalize("NFC", value.strip())
        if kind == "phone":
            value = re.sub(r"[\s.()-]", "", value)
            if not re.fullmatch(rule["pattern"], value):
                raise ValueError("Số điện thoại cần đúng 10 chữ số, bắt đầu bằng 0")
        elif kind == "email":
            if len(value) > rule["max_length"] or not re.fullmatch(
                r"[^\s@]+@[^\s@]+\.[^\s@]+", value
            ):
                raise ValueError("Email không đúng định dạng")
        elif kind == "date":
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise ValueError("Ngày bắt đầu cần định dạng YYYY-MM-DD")
            date.fromisoformat(value)
        elif kind == "choice" and value not in rule["choices"]:
            raise ValueError("Giá trị ngoài danh sách cho phép")
        elif kind == "text" and not rule.get("min_length", 1) <= len(value) <= rule["max_length"]:
            raise ValueError("Độ dài thông tin không hợp lệ")
        return value

    def record(self, session_id, job_id=""):
        if job_id:
            self.job(job_id, active=False)
        rows = [
            row
            for row in self.store.read("candidate_profiles").values()
            if row["agent_id"] == self.agent_id
            and row["session_id"] == session_id
            and (not job_id or row["job_id"] == job_id)
        ]
        return max(rows, key=lambda row: row["selected_at"]) if rows else None

    def profile(self, session_id, job_id=""):
        row = self.record(session_id, job_id)
        return (
            {**row["collected"], **({"job_id": row["job_id"]} if row["job_id"] else {})}
            if row
            else {}
        )

    def missing(self, profile):
        return [field for field in self.required_fields if not present(profile.get(field))]

    def write_profile(self, session_id, patch):
        patch = {key: self.validate(key, value) for key, value in patch.items()}
        requested_job = patch.get("job_id")

        def apply(items):
            rows = [
                row
                for row in items.values()
                if row["agent_id"] == self.agent_id and row["session_id"] == session_id
            ]
            matching = (
                [row for row in rows if row["job_id"] == requested_job] if requested_job else rows
            )
            row = max(matching, key=lambda value: value["selected_at"]) if matching else None
            if row is None and requested_job:
                drafts = [value for value in rows if value["job_id"] is None]
                row = max(drafts, key=lambda value: value["selected_at"]) if drafts else None
            if row is None:
                row = {
                    "application_id": uuid4().hex,
                    "agent_id": self.agent_id,
                    "session_id": session_id,
                    "job_id": None,
                    "collected": {},
                    "profile_version": 0,
                    "crm_contact_id": None,
                }
                items[row["application_id"]] = row
            before = {"job_id": row["job_id"], "collected": dict(row["collected"])}
            if requested_job:
                row["job_id"] = requested_job
            row["collected"].update({key: value for key, value in patch.items() if key != "job_id"})
            if before != {"job_id": row["job_id"], "collected": row["collected"]}:
                row["profile_version"] += 1
                row["updated_at"] = now()
            row["selected_at"] = now()
            return row

        row = self.store.update("candidate_profiles", apply)
        profile = {**row["collected"], **({"job_id": row["job_id"]} if row["job_id"] else {})}
        return {
            "saved": True,
            "application_id": row["application_id"],
            "profile_version": row["profile_version"],
            "profile": profile,
            "updated_fields": list(patch),
            "missing_fields": self.missing(profile),
        }

    def notes(self, session_id):
        return sorted(
            [
                row
                for row in self.store.read("candidate_notes").values()
                if row["agent_id"] == self.agent_id and row["session_id"] == session_id
            ],
            key=lambda row: row["created_at"],
        )

    def add_note(self, session_id, text, *, author="agent", kind="candidate_note", request_key=""):
        row = self.record(session_id)
        return self.client.create_private_message(
            session_id,
            text,
            agent_id=self.agent_id,
            kind=kind,
            author=author,
            request_key=request_key,
            application_id=row["application_id"] if row else None,
        )

    def snapshot(self, row):
        job = self.job(row["job_id"])
        snapshot = {
            "collected": row["collected"],
            "job_id": row["job_id"],
            "job_version": job["version"],
            "evaluation_policy": job["evaluation_policy"],
            "required_fields": self.required_fields,
            "job_preferences": {"location": job["location"], "shift": job["shift"]},
        }
        return snapshot, fingerprint(snapshot)

    def evaluate(self, session_id, job_id=""):
        row = self.record(session_id, job_id)
        if not row or not row["job_id"]:
            raise ValueError("Cần chọn vị trí và lưu hồ sơ trước khi đánh giá")
        snapshot, snapshot_hash = self.snapshot(row)
        key = fingerprint([row["application_id"], snapshot_hash])
        cached = self.store.read("candidate_evaluations").get(key)
        if cached:
            return {**cached, "cached": True}
        job = self.job(row["job_id"])
        policy = job["evaluation_policy"]
        profile = row["collected"]
        scores = {}
        for field in policy["criteria"]:
            value = profile.get(field)
            score = None
            if present(value):
                if field == "experience_years":
                    score = 5 if value >= policy["minimum_experience_years"] else 1
                elif field == "skills":
                    desired = policy["desired_skills"]
                    score = (
                        5
                        if not desired
                        or any(normalized(skill) in normalized(value) for skill in desired)
                        else 2
                    )
                elif field == "preferred_shift":
                    score = 5 if value in {job["shift"], "any"} else 1
                elif field == "preferred_location":
                    score = 5 if normalized(value) in normalized(job["location"]) else 1
                elif field == "available_date":
                    score = 5  # Valid self-reported date; no inferred commitment or health score.
            scores[field] = {"score": score, "evidence": value}
        hard_missing = self.missing({**profile, "job_id": row["job_id"]})
        unknown = [field for field, value in scores.items() if value["score"] is None]
        total = sum(value["score"] or 0 for value in scores.values())
        decision = (
            "HOLD"
            if hard_missing or unknown
            else "PROCEED"
            if total >= policy["proceed_score"]
            else "REJECT"
            if total < policy["reject_below_score"]
            else "HOLD"
        )
        result = {
            "evaluation_id": key,
            "application_id": row["application_id"],
            "session_id": session_id,
            "agent_id": self.agent_id,
            "job_id": row["job_id"],
            "profile_snapshot_hash": snapshot_hash,
            "profile_snapshot": snapshot,
            "profile_version": row["profile_version"],
            "evaluation_policy_version": policy["version"],
            "job_version": job["version"],
            "scores": scores,
            "total_score": total,
            "decision": decision,
            "hard_missing": hard_missing,
            "unassessed_fields": unknown,
            "simulation": True,
            "requires_hr_review": True,
            "ai_initial_assessment": f"MÔ PHỎNG: {decision}; {total}/25 điểm; cần HR xem xét, chưa phải kết quả tuyển dụng.",
            "evaluated_at": now(),
        }
        self.store.update("candidate_evaluations", lambda items: items.setdefault(key, result))
        return {**result, "cached": False}

    def sync(self, session_id, job_id=""):
        row = self.record(session_id, job_id)
        if not row or not row["job_id"]:
            return {"synced": False, "error": "Chưa có hồ sơ gắn với vị trí"}
        assessment = self.evaluate(session_id, row["job_id"])
        if assessment["hard_missing"]:
            return {"synced": False, "hard_missing": assessment["hard_missing"]}
        key = assessment["evaluation_id"]
        operation = self.store.read("crm_sync_operations").get(key)
        if operation and operation["status"] == "succeeded":
            return {
                "synced": True,
                "is_mock": True,
                "cached": True,
                "operation_id": key,
                "contact_id": operation["contact_id"],
            }
        payload = {
            "application_id": row["application_id"],
            "contact_id": row["crm_contact_id"],
            "job_id": row["job_id"],
            "collected": row["collected"],
            "profile_snapshot_hash": assessment["profile_snapshot_hash"],
            "ai_initial_assessment": assessment["ai_initial_assessment"],
        }
        operation = {
            "operation_id": key,
            "application_id": row["application_id"],
            "agent_id": self.agent_id,
            "session_id": session_id,
            "status": "pending",
            "payload": payload,
            "attempts": (operation or {}).get("attempts", 0) + 1,
            "updated_at": now(),
            "error": None,
        }
        self.store.update("crm_sync_operations", lambda items: items.update({key: operation}))
        try:
            contact = self.client.update_contact_info(payload)
        except (OSError, ValueError, RuntimeError) as exc:
            operation.update(status="failed", error=str(exc), updated_at=now())
            self.store.update("crm_sync_operations", lambda items: items.update({key: operation}))
            return {
                "synced": False,
                "is_mock": True,
                "operation_id": key,
                "error": "CRM giả lập chưa cập nhật, có thể thử lại",
            }
        contact_id = contact["contact_id"]
        self.store.update(
            "candidate_profiles",
            lambda items: items[row["application_id"]].update(crm_contact_id=contact_id),
        )
        operation.update(status="succeeded", contact_id=contact_id, updated_at=now())
        self.store.update("crm_sync_operations", lambda items: items.update({key: operation}))
        return {
            "synced": True,
            "is_mock": True,
            "cached": False,
            "operation_id": key,
            "contact_id": contact_id,
        }

    def hr_details(self, session_id):
        applications = [
            row
            for row in self.store.read("candidate_profiles").values()
            if row["agent_id"] == self.agent_id and row["session_id"] == session_id
        ]
        current = self.record(session_id)
        assessment = None
        snapshot_hash = None
        if current and current["job_id"]:
            try:
                _, snapshot_hash = self.snapshot(current)
                assessment = self.store.read("candidate_evaluations").get(
                    fingerprint([current["application_id"], snapshot_hash])
                )
            except ValueError:
                pass  # Closed jobs have no current assessment; historical rows remain on disk.
        operations = [
            row
            for row in self.store.read("crm_sync_operations").values()
            if row["agent_id"] == self.agent_id
            and row["session_id"] == session_id
            and current
            and row["application_id"] == current["application_id"]
        ]
        operation = max(operations, key=lambda row: row["updated_at"]) if operations else None
        if operation:
            operation["is_current_snapshot"] = (
                operation["payload"]["profile_snapshot_hash"] == snapshot_hash
            )
        return {
            "applications": applications,
            "notes": self.notes(session_id),
            "evaluation": assessment,
            "crm_sync": operation,
        }


class SessionProfiles(MutableMapping):
    """Compatibility view for the demo UI: the currently selected job per session."""

    def __init__(self, data: RecruitmentData):
        self.data = data

    def __getitem__(self, key):
        if self.data.record(key) is None:
            raise KeyError(key)
        return self.data.profile(key)

    def __setitem__(self, key, value):
        self.data.write_profile(key, value)

    def __delitem__(self, key):
        def remove(items):
            for identifier in [
                identifier
                for identifier, row in items.items()
                if row["session_id"] == key and row["agent_id"] == self.data.agent_id
            ]:
                del items[identifier]

        self.data.store.update("candidate_profiles", remove)

    def __iter__(self):
        return iter(
            {
                row["session_id"]
                for row in self.data.store.read("candidate_profiles").values()
                if row["agent_id"] == self.data.agent_id
            }
        )

    def __len__(self):
        return len(list(iter(self)))
