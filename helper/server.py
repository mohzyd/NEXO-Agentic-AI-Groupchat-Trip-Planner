from utils import Pipes

def create_server_listeners() -> None:

    @Pipes.add_listener
    def has_job(connection_id: str, data: dict) -> None:
        job = data.get("job", "")

        if not isinstance(job, str) or len(job.strip()) == 0:
            return

        is_exists = Pipes.has_job(job)
        
        Pipes.send(
            {"exists": is_exists},
            listener="server_has_job_response",
            to_pipe_id=connection_id,
            sync=True
        )