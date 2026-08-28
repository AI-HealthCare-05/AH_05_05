from pathlib import Path

from cryptography.fernet import Fernet

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT / ".env"
SETTING_NAME = "PHONE_ENCRYPTION_KEY"


def main() -> None:
    if not ENV_FILE.exists():
        raise SystemExit(f"{ENV_FILE} 파일이 없습니다. .env.example을 먼저 복사하세요.")

    lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    for line in lines:
        if line.startswith(f"{SETTING_NAME}=") and line.partition("=")[2].strip():
            print(f"{SETTING_NAME}는 이미 설정되어 있습니다. 기존 키를 유지합니다.")
            return

    generated_key = Fernet.generate_key().decode("ascii")
    replacement = f"{SETTING_NAME}={generated_key}"
    replaced = False
    updated_lines = []
    for line in lines:
        if line.startswith(f"{SETTING_NAME}="):
            updated_lines.append(replacement)
            replaced = True
        else:
            updated_lines.append(line)
    if not replaced:
        updated_lines.extend(["", "# user 개인정보 암호화", replacement])

    ENV_FILE.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
    print(f"{SETTING_NAME}를 .env에 생성했습니다. 키는 별도 보안 저장소에 백업하세요.")


if __name__ == "__main__":
    main()
