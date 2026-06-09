"""历史数据迁移脚本。将现有 txt/json 文件导入 PostgreSQL。

Usage:
    python scripts/migrate_legacy_data.py --emails emails.txt --platform outlook
    python scripts/migrate_legacy_data.py --cookies cookies/claude/ --platform claude
    python scripts/migrate_legacy_data.py --outlook-pool _outlook_pool/
"""
import argparse
import json
import os
import sys
import glob

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'services'))


def parse_emails_txt(filepath: str) -> list[dict]:
    """解析 email----password----token----client_id 格式。"""
    accounts = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split('----')
            account = {
                'email': parts[0] if len(parts) > 0 else '',
                'password': parts[1] if len(parts) > 1 else '',
                'tokens': {},
            }
            if len(parts) > 2 and parts[2]:
                account['tokens']['refresh_token'] = parts[2]
            if len(parts) > 3 and parts[3]:
                account['tokens']['client_id'] = parts[3]
            if account['email']:
                accounts.append(account)
    return accounts


def parse_cookies_dir(dirpath: str) -> list[dict]:
    """解析 cookies/platform/full_*.json 文件。"""
    accounts = []
    for filepath in glob.glob(os.path.join(dirpath, 'full_*.json')):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                cookies = json.load(f)
            filename = os.path.basename(filepath)
            email = filename.replace('full_', '').replace('.json', '').replace('_', '@', 1)
            accounts.append({
                'email': email,
                'cookies': cookies,
                'status': 'success',
            })
        except Exception as e:
            print(f"  Skip {filepath}: {e}")
    return accounts


def parse_outlook_pool(dirpath: str) -> list[dict]:
    """解析 _outlook_pool/*.json 文件。"""
    accounts = []
    for filepath in glob.glob(os.path.join(dirpath, '*.json')):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            accounts.append({
                'email': data.get('email', ''),
                'password': data.get('password', ''),
                'tokens': {
                    'refresh_token': data.get('refresh_token', ''),
                    'client_id': data.get('client_id', ''),
                },
                'status': 'success',
            })
        except Exception as e:
            print(f"  Skip {filepath}: {e}")
    return accounts


def main():
    parser = argparse.ArgumentParser(description='迁移历史数据到 PostgreSQL')
    parser.add_argument('--emails', help='emails.txt 文件路径')
    parser.add_argument('--cookies', help='cookies 目录路径')
    parser.add_argument('--outlook-pool', help='_outlook_pool 目录路径')
    parser.add_argument('--platform', default='outlook', help='平台名称')
    parser.add_argument('--dry-run', action='store_true', help='仅预览，不写入')
    args = parser.parse_args()

    all_accounts = []

    if args.emails:
        print(f"解析 {args.emails}...")
        accounts = parse_emails_txt(args.emails)
        print(f"  找到 {len(accounts)} 个账户")
        all_accounts.extend(accounts)

    if args.cookies:
        print(f"解析 {args.cookies}...")
        accounts = parse_cookies_dir(args.cookies)
        print(f"  找到 {len(accounts)} 个账户")
        all_accounts.extend(accounts)

    if args.outlook_pool:
        print(f"解析 {args.outlook_pool}...")
        accounts = parse_outlook_pool(args.outlook_pool)
        print(f"  找到 {len(accounts)} 个账户")
        all_accounts.extend(accounts)

    print(f"\n总计 {len(all_accounts)} 个账户待导入（平台: {args.platform}）")

    if args.dry_run:
        print("\n[DRY RUN] 仅预览，未写入数据库")
        for i, a in enumerate(all_accounts[:5]):
            print(f"  {i+1}. {a['email']}")
        if len(all_accounts) > 5:
            print(f"  ... 还有 {len(all_accounts) - 5} 个")
        return

    print("\n要写入数据库，请去掉 --dry-run 参数。")
    print("（需要先启动 PostgreSQL 并运行 Alembic 迁移）")


if __name__ == '__main__':
    main()
