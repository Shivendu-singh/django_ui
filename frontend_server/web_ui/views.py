import token
import requests
import re
import json
import os
import base64
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages 

GO_BACKEND_URL = os.getenv('GO_BACKEND_URL','http://127.0.0.1:8080')


def get_current_user_id(request):
    """Extract user ID — session cache first, JWT fallback."""
    if request.session.get('user_id'):
        return int(request.session['user_id'])
    
    token = request.session.get("auth_token")
    if not token:
        return None
    
    try:
        parts = token.split('.')
        if len(parts) < 2: return None
        # Fix padding
        payload = parts[1] + '=' * (-len(parts[1]) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
        return int(data.get('user_id'))
    except Exception as e:
        print(f"Token decode error: {e}")
        return None

def get_current_username(request):
    """Extract username — session cache first, JWT fallback."""
    if request.session.get('username'):
        return request.session['username']
    
    token = request.session.get("auth_token")
    if not token:
        return None
    
    try:
        parts = token.split('.')
        if len(parts) < 2: return None
        payload = parts[1] + '=' * (-len(parts[1]) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
        return data.get('username', f"User {data.get('user_id', '?')}")
    except Exception:
        return None


def signup_page(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        confirm_password = request.POST.get('ConfirmPassword')

        payload = {
            "username": username,
            "email": email,
            "password": password,
            "confirm_password": confirm_password
        }

        try:
            response = requests.post(f"{GO_BACKEND_URL}/api/signup", json=payload)
            print(f"Signup response: {response.status_code} - {response.text}")
            if response.status_code in [200, 201]:
                messages.success(request, "Account created! Please log in.")
                return redirect('login')
            else:
                error_msg = response.json().get('error', 'Signup failed')
                return render(request, 'web_ui/signup.html', {'error': error_msg})

        except requests.exceptions.ConnectionError:
            return render(request, 'web_ui/signup.html', {'error': 'Cannot connect to Backend Server'})

    return render(request, 'web_ui/signup.html')


def login_page(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')

        payload = {
            "email": email,
            "password": password
        }

        try:
            response = requests.post(f"{GO_BACKEND_URL}/api/login", json=payload)

            if response.status_code == 200:
                try:
                    data = response.json()
                    token = data.get('token')
                except ValueError:
                    return render(request, 'web_ui/login.html', {'error': 'Backend returned invalid JSON'})

            
                request.session['auth_token'] = token
                request.session['user_email'] = email

               
                try:
                    parts = token.split('.')
                    padded = parts[1] + '=' * (-len(parts[1]) % 4)
                    jwt_data = json.loads(base64.urlsafe_b64decode(padded))
                    if jwt_data.get('user_id'):
                        request.session['user_id'] = int(jwt_data['user_id'])
                except Exception:
                    pass

                try:
                    headers = {"Authorization": f"Bearer {token}"}
                    uid = request.session.get('user_id')
                    groups_res = requests.get(f"{GO_BACKEND_URL}/api/groups", headers=headers)
                    if groups_res.status_code == 200:
                        groups = groups_res.json() or []
                        if groups:
                            # Fetch members of the first group to find self
                            members_res = requests.get(
                                f"{GO_BACKEND_URL}/api/groups/{groups[0]['id']}/members",
                                headers=headers
                            )
                            if members_res.status_code == 200:
                                for m in (members_res.json() or []):
                                    if m['id'] == uid:
                                        request.session['username'] = m['username']
                                        break
                except Exception:
                    pass

                return redirect('dashboard')
            else:
                try:
                    err = response.json().get('error', 'Login failed')
                except ValueError:
                    err = f"Login failed ({response.status_code})"
                return render(request, 'web_ui/login.html', {'error': err})

        except requests.exceptions.ConnectionError:
            return render(request, 'web_ui/login.html', {'error': 'Cannot connect to Backend Server'})

    return render(request, 'web_ui/login.html')


def logout_user(request):
    request.session.flush()
    messages.success(request, "You have been logged out.")
    return redirect('login')



def dashboard_page(request):
    token = request.session.get('auth_token')
    if not token:
        messages.error(request, "You must log in to view the dashboard.")
        return redirect('login')

    headers = {'Authorization': f'Bearer {token}'}

    try:
        response = requests.get(f"{GO_BACKEND_URL}/api/dashboard", headers=headers)

        if response.status_code == 200:
            return render(request, 'web_ui/dashboard.html', {
                'data': response.json(),
                'user_email': request.session.get('user_email')
            })
        elif response.status_code == 401:
            messages.error(request, "Session expired. Please login again.")
            return redirect('login')
        else:
            return render(request, 'web_ui/dashboard.html', {'error': 'Could not fetch dashboard data'})

    except requests.exceptions.ConnectionError:
        return render(request, 'web_ui/dashboard.html', {'error': 'Backend is offline'})


def home(request):
    token = request.session.get("auth_token")
    groups = []

    if token:
        headers = {"Authorization": f"Bearer {token}"}
        try:
            res = requests.get(f"{GO_BACKEND_URL}/api/groups", headers=headers)
            if res.status_code == 200:
                groups = res.json()
        except:
            pass

    return render(request, "web_ui/home.html", {
        "is_logged_in": bool(token),
        "groups": groups
    })


def create_group(request):
    token = request.session.get("auth_token")
    if not token: return redirect("login")

    if request.method == "POST":
        name = request.POST.get("name")
        headers = {"Authorization": f"Bearer {token}"}

        try:
            res = requests.post(
                f"{GO_BACKEND_URL}/api/create-group",
                json={"name": name},
                headers=headers
            )
            
            if res.status_code == 200:
                data = res.json()
                return render(request, "web_ui/group_created.html", {"code": data["join_code"]})
            else:
                error_msg = res.json().get('error', f'Error {res.status_code}')
                return render(request, "web_ui/create_group.html", {"error": error_msg})

        except requests.exceptions.ConnectionError:
            return render(request, "web_ui/create_group.html", {"error": "Cannot connect to Backend Server"})

    return render(request, "web_ui/create_group.html")


def join_group(request):
    token = request.session.get("auth_token")
    if not token: return redirect("login")

    if request.method == "POST":
        code = request.POST.get("code")
        headers = {"Authorization": f"Bearer {token}"}

        try:
            res = requests.post(
                f"{GO_BACKEND_URL}/api/join-group",
                json={"code": code},
                headers=headers
            )
            
            if res.status_code == 200:
                messages.success(request, "Joined group successfully!")
                return redirect("home")
            else:
                # Capture specific error (e.g., "invalid code")
                err = res.json().get("error", "Failed to join group")
                messages.error(request, err)
        except requests.exceptions.ConnectionError:
            messages.error(request, "Backend unavailable")

    return render(request, "web_ui/join_group.html")


def add_expense(request, group_id):
    token = request.session.get("auth_token")
    if not token: return redirect("login")
    headers = {"Authorization": f"Bearer {token}"}

    members = []
    debug_error = None  # <--- New variable to capture errors

    # 1. Fetch Members with Error Capture
    try:
        members_url = f"{GO_BACKEND_URL}/api/groups/{group_id}/members"
        res = requests.get(members_url, headers=headers)
        
        if res.status_code == 200:
            members = res.json() or []
        else:
            # Capture backend error (e.g., 404 or 500)
            debug_error = f"Backend Error {res.status_code}: {res.text}"
            
    except requests.exceptions.ConnectionError:
        debug_error = f"Connection Refused. Is Go running at {GO_BACKEND_URL}?"
    except Exception as e:
        debug_error = f"Python Exception: {str(e)}"

    # 2. Process POST (Save Expense)
    if request.method == "POST":
        amount_str = request.POST.get("amount")
        description = request.POST.get("description")
        split_mode = request.POST.get("split_mode")
        
        try:
            total_amount = float(amount_str)
        except:
            total_amount = 0.0

        splits = []

        # LOGIC: Equal All
        if split_mode == "equal_all":
            if members:
                count = len(members)
                share = round(total_amount / count, 2)
                rem = round(total_amount - (share * count), 2)
                for i, m in enumerate(members):
                    amt = share + rem if i == 0 else share
                    splits.append({"user_id": int(m['id']), "amount": float(f"{amt:.2f}")})
            else:
                messages.error(request, "Cannot split: No members found.")

        # LOGIC: Equal Subset
        elif split_mode == "equal_subset":
            selected_ids = request.POST.getlist("selected_members")
            if not selected_ids:
                messages.error(request, "Please select at least one member.")
                return render(request, "web_ui/add_expense.html", {"group_id": group_id, "members": members, "debug_error": debug_error})
            
            count = len(selected_ids)
            share = round(total_amount / count, 2)
            rem = round(total_amount - (share * count), 2)
            
            for i, uid in enumerate(selected_ids):
                amt = share + rem if i == 0 else share
                splits.append({"user_id": int(uid), "amount": float(f"{amt:.2f}")})

        # LOGIC: Custom Split
        elif split_mode == "custom":
            custom_total = 0.0
            for m in members:
                val = request.POST.get(f"custom_amount_{m['id']}")
                if val: 
                    try:
                        amt = float(val)
                        if amt > 0: 
                            splits.append({"user_id": int(m['id']), "amount": amt})
                            custom_total += amt
                    except: pass
            
            if abs(custom_total - total_amount) > 0.01:
                messages.error(request, f"Total ({custom_total}) does not match Amount ({total_amount})")
                return render(request, "web_ui/add_expense.html", {"group_id": group_id, "members": members, "debug_error": debug_error})

        payload = {
            "group_id": int(group_id),
            "amount": total_amount,
            "description": description,
            "splits": splits
        }
        
        try:
            res = requests.post(f"{GO_BACKEND_URL}/api/expenses", json=payload, headers=headers)
            if res.status_code in [200, 201]:
                messages.success(request, "Expense added successfully!")
                return redirect("home")
            else:
                messages.error(request, f"Backend Error: {res.text}")
        except:
            messages.error(request, "Backend unavailable during save.")

    # Pass 'debug_error' to the template
    return render(request, "web_ui/add_expense.html", {
        "group_id": group_id, 
        "members": members,
        "debug_error": debug_error
    })


def simplify_group(request, group_id):
    token = request.session.get("auth_token")
    if not token: return redirect('login')
    
    headers = {"Authorization": f"Bearer {token}"}
    txns = []
    my_id = get_current_user_id(request)

    try:
        res = requests.get(f"{GO_BACKEND_URL}/api/groups/{group_id}/simplify", headers=headers)
        if res.status_code == 200:
            all_txns = res.json() or []
            # Filter for current user only
            if my_id:
                txns = [t for t in all_txns if t.get('from') == my_id or t.get('to') == my_id]
            else:
                txns = all_txns
    except Exception as e:
        print(f"Error fetching debts: {e}")

    return render(request, "web_ui/simplify.html", {
        "txns": txns,
        "group_id": group_id
    })


def settle_debt(request, group_id):
    token = request.session.get("auth_token")
    if not token: return redirect('login')

    if request.method == "POST":
        payee_id = request.POST.get('payee_id')
        payee_name = request.POST.get('payee_name')
        amount = request.POST.get('amount')

        headers = {"Authorization": f"Bearer {token}"}
        
        # CORRECTED PAYLOAD for Settlement Endpoint
        payload = {
            "group_id": int(group_id),
            "payee_id": int(payee_id),
            "amount": float(amount)
        }

        try:
            # CORRECTED URL: Hits /api/settlements
            response = requests.post(
                f"{GO_BACKEND_URL}/api/settlements",
                json=payload,
                headers=headers
            )

            if response.status_code in [200, 201]:
                messages.success(request, f"Paid ₹{amount} to {payee_name}")
            else:
                messages.error(request, f"Error: {response.text}")

        except requests.exceptions.ConnectionError:
            messages.error(request, "Backend unavailable.")

    return redirect('simplify', group_id=group_id)


def group_expenses(request, group_id):
    token = request.session.get("auth_token")
    if not token: return redirect('login')
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # 1. Helper to map User IDs to Names
    user_map = {}
    try:
        res_members = requests.get(f"{GO_BACKEND_URL}/api/groups/{group_id}/members", headers=headers)
        if res_members.status_code == 200:
            for m in (res_members.json() or []):
                user_map[m['id']] = m['username']
    except:
        pass

    # 2. Fetch Activity
    activity = []
    try:
        res_act = requests.get(f"{GO_BACKEND_URL}/api/groups/{group_id}/activity", headers=headers)
        if res_act.status_code == 200:
            data = res_act.json()
            activity = data.get('activity_feed', [])
    except:
        pass

    # 3. Format for Template
    payload = []
    for item in activity:
        payer_id = item.get('payer_id')
        payee_id = item.get('payee_id') # Usually 0 for expenses, valid ID for settlements

        payer_name = user_map.get(payer_id, f"User {payer_id}")
        payee_name = user_map.get(payee_id, f"User {payee_id}")

        description = item.get('description', '')
        # Simple heuristic to detect settlement if payee_id is used
        is_settlement = (payee_id is not None and payee_id != 0) or ('Payment to' in description)

        payload.append({
            "amount": item.get('amount'),
            "description": description,
            "created_at": item.get('created_at'),
            "payer_name": payer_name,
            "payee_name": payee_name,
            "is_settlement": is_settlement
        })

    return render(request, "web_ui/group_expenses.html", {
        "expenses": payload,
        "group_id": group_id
    })


def chat_page(request, group_id):
    # print("page called")
    token = request.session.get("auth_token")
    if not token: return redirect('login')
    headers = {"Authorization": f"Bearer {token}"}
    # print(f"Fetching chat history for group {group_id} with token: {token}")
    chat_history = []
    user_id = get_current_user_id(request)
    username = get_current_username(request)
    try:
        response = requests.get(f"{GO_BACKEND_URL}/api/groups/{group_id}/activity", headers=headers)
        # print(f"Activity response status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            # print("Raw activity data:", data);
            # Extract the chat specific part from the combined JSON
            chat_history = data.get('chat_history', [])
            # print(f"Fetched chat history: {chat_history}")
    except:
        pass

    # print("DEBUG chat_history:", chat_history)
    ws_url = os.getenv("WS_BACKEND_URL", "ws://localhost:8080")

    return render(request, "web_ui/chat.html", {
        "go_backend_url": GO_BACKEND_URL,
        "ws_backend_url": ws_url,
        "token": token,
        "group_id": group_id,
        "user_id": user_id,
        "username": username,
        "chat_history": json.dumps(chat_history),
        "cloud_name": os.getenv("CLOUDINARY_CLOUD_NAME"),
        "upload_preset": os.getenv("CLOUDINARY_UPLOAD_PRESET")
    })