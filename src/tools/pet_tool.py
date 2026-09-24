import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from dotenv import load_dotenv
import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

BUSINESS_API_BASE_URL = os.getenv("BUSINESS_API_BASE_URL", "http://127.0.0.1:3001").rstrip("/")


def register_pet(
    pet_type: str,
    name: str,
    area: str,
    breed: Optional[str] = None,
    age: Optional[str] = None,
    health_status: Optional[str] = None,
    health: Optional[str] = None,
    image_url: Optional[str] = None,
    auth_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    向管理系统登记流浪动物（猫咪/狗狗）。
    安全规范：必须携带有效的认证令牌（Token），通过业务端权限校验（pet:write）完成写入。
    """
    pet_type_value = pet_type.strip().lower() if isinstance(pet_type, str) else ""
    if pet_type_value not in {"cat", "dog", "猫", "猫咪", "狗", "狗狗"}:
        return {
            "success": False,
            "channel": "invalid_fields",
            "message": "动物类型只能是猫或狗，数据未提交。",
        }

    is_cat = pet_type_value in {"cat", "猫", "猫咪"}
    table = "cats" if is_cat else "dogs"
    pet_label = "猫咪" if is_cat else "狗狗"

    # 严格鉴权安全拦截：无 Token 场景直接失败，禁止越权写库
    if not auth_token or not str(auth_token).strip():
        return {
            "success": False,
            "channel": "auth_required",
            "message": f"【权限校验失败】未检测到登录令牌（Token），无权限向管理系统登记{pet_label}。请登录具有管理权限的账号后再试。",
        }

    required_fields = {
        "名称": name,
        "所在区域": area,
        "品种": breed,
        "年龄": age,
        "健康状态": health_status,
        "健康描述": health,
    }
    validated_fields: dict[str, str] = {}
    missing_fields = []
    for label, value in required_fields.items():
        cleaned = value.strip() if isinstance(value, str) else ""
        if cleaned:
            validated_fields[label] = cleaned
        else:
            missing_fields.append(label)
    if missing_fields:
        return {
            "success": False,
            "channel": "missing_fields",
            "message": f"缺少必填信息：{'、'.join(missing_fields)}。请向用户核实后再提交，数据未写入。",
        }

    final_name = validated_fields["名称"]
    final_area = validated_fields["所在区域"]
    final_breed = validated_fields["品种"]
    final_age = validated_fields["年龄"]
    final_health_status = validated_fields["健康状态"]
    final_health = validated_fields["健康描述"]
    found_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    api_endpoint = f"{BUSINESS_API_BASE_URL}/api/admin/{table}"
    formatted_token = auth_token if auth_token.startswith("Bearer ") else f"Bearer {auth_token}"
    headers = {
        "Content-Type": "application/json",
        "Authorization": formatted_token,
    }

    payload = {
        "name": final_name,
        "age": final_age,
        "breed": final_breed,
        "healthStatus": final_health_status,
        "health": final_health,
        "area": final_area,
        "imageUrl": image_url,
        "foundTime": found_time,
    }

    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(api_endpoint, json=payload, headers=headers)
            
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success"):
                    insert_id = data.get("data", {}).get("id")
                    return {
                        "success": True,
                        "channel": "api",
                        "message": f"【系统提示】已成功通过业务系统登记{pet_label}【{final_name}】（档案编号 #{insert_id}）！所在区域：{final_area}，品种：{final_breed}，健康状况：{final_health_status}。",
                        "id": insert_id,
                    }
                else:
                    return {
                        "success": False,
                        "channel": "api_error",
                        "message": f"【业务提示】登记{pet_label}失败：{data.get('msg', '业务接口拒绝了该请求')}",
                    }
            elif resp.status_code == 401:
                return {
                    "success": False,
                    "channel": "unauthorized",
                    "message": "【认证失败】登录令牌已失效或已过期，请重新登录。",
                }
            elif resp.status_code == 403:
                return {
                    "success": False,
                    "channel": "forbidden",
                    "message": f"【权限不足】当前登录账号暂无流浪动物登记（pet:write）权限，无法写入数据。",
                }
            else:
                return {
                    "success": False,
                    "channel": "api_error",
                    "message": f"【接口错误】业务接口返回异常状态码 {resp.status_code}：{resp.text}",
                }
    except httpx.RequestError as req_err:
        return {
            "success": False,
            "channel": "connection_error",
            "message": f"【服务异常】无法连接业务后端服务（{BUSINESS_API_BASE_URL}）：{str(req_err)}，数据未能写入。",
        }
    except Exception as e:
        return {
            "success": False,
            "channel": "unexpected_error",
            "message": f"【未知异常】登记流浪动物时发生错误：{str(e)}",
        }


def query_pets(
    pet_type: str = "cat",
    keyword: Optional[str] = None,
    area: Optional[str] = None,
    limit: int = 5,
) -> Dict[str, Any]:
    """
    查询流浪动物图鉴（只读公开信息，优先调用业务端 /api/app 接口）
    """
    is_cat = any(cat_kw in pet_type.lower() for cat_kw in ["cat", "猫"])
    endpoint_name = "cats" if is_cat else "dogs"
    pet_label = "猫咪" if is_cat else "狗狗"

    api_url = f"{BUSINESS_API_BASE_URL}/api/app/{endpoint_name}"
    params: Dict[str, Any] = {"page": 1, "pageSize": limit}
    if keyword:
        params["keyword"] = keyword
    if area:
        params["area"] = area

    try:
        with httpx.Client(timeout=4.0) as client:
            resp = client.get(api_url, params=params)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success"):
                    pet_list = data.get("data", {}).get("list", [])
                    return {
                        "success": True,
                        "count": len(pet_list),
                        "list": pet_list,
                        "message": f"共查询到 {len(pet_list)} 只相关的{pet_label}。" if pet_list else f"暂未找到符合条件的{pet_label}。",
                    }
    except Exception:
        pass

    return {
        "success": False,
        "message": f"暂无法连接业务服务查询{pet_label}列表。",
    }
