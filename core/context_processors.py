def employee_context(request):
    employee = None
    if request.user.is_authenticated:
        try:
            employee = request.user.employee
        except Exception:
            pass
    return {"current_employee": employee}
