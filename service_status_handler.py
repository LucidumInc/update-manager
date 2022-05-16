import subprocess


class BaseServiceStatusHandler:
    service_name = None

    def get_status(self) -> dict:
        raise NotImplementedError

    def get_service_info(self, service_name: str) -> dict:
        command = f"systemctl show {service_name} --no-page"
        result = subprocess.run(
            command.split(), check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True
        )
        lines = result.stdout.splitlines()
        result = {}
        for line in lines:
            key, value = line.split("=", 1)
            result[key] = value
        return result

    @classmethod
    def get_service_status_handlers(cls):
        return cls.__subclasses__()


class AirflowSchedulerStatusHandler(BaseServiceStatusHandler):
    service_name = "airflow-scheduler"

    def get_status(self) -> dict:
        service_info = self.get_service_info("airflow-scheduler")
        return {
            "service": self.service_name,
            "active_state": service_info["ActiveState"],
            "sub_state": service_info["SubState"],
        }


class AirflowWebserverStatusHandler(BaseServiceStatusHandler):
    service_name = "airflow-webserver"

    def get_status(self) -> dict:
        service_info = self.get_service_info("airflow-webserver")
        return {
            "service": self.service_name,
            "active_state": service_info["ActiveState"],
            "sub_state": service_info["SubState"],
        }


def get_services_statuses() -> list:
    services_handlers_clss = BaseServiceStatusHandler.get_service_status_handlers()
    result = []
    for service_handler_cls in services_handlers_clss:
        service_handler = service_handler_cls()
        status = service_handler.get_status()
        result.append(status)
    return result
