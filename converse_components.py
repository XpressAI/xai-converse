from xai_components.base import InArg, OutArg, InCompArg, Component, AsyncComponent, BaseComponent, xai_component, \
    SubGraphExecutor
import inspect
from pathlib import Path
import time
import secrets
import random
import string
import json

from quart import Quart, Response, request, jsonify, redirect, abort, send_file, stream_with_context
from quart.views import View
from quart_cors import cors

import asyncio


CONVERSE_APP_KEY = "quart_app"
CONVERSE_AGENTS_KEY = "converse_agents"
CONVERSE_RES_KEY = "converse_res"

alphabet = string.ascii_letters + string.digits


def random_string(length):
    return ''.join(random.choice(string.ascii_letters) for _ in range(length))


def make_id():
    return ''.join(secrets.choice(alphabet) for i in range(29))


def make_content_response(model_name, chat_id, created, content):
    return json.dumps({
        "choices": [
            {
                "delta": {
                    "content": content
                },
                "finish_reason": None,
                "index": 0
            }
        ],
        "created": created,
        "id": chat_id,
        "model": model_name,
        "object": "chat.completion.chunk"
    })


def make_finish_response(model_name, chat_id, created):
    return json.dumps({
        "choices": [
            {
                "delta": {},
                "finish_reason": "stop",
                "index": 0
            }
        ],
        "created": created,
        "id": chat_id,
        "model": model_name,
        "object": "chat.completion.chunk"
    })


class SendFileRoute(View):
    def __init__(self, base_dir, default_file_path):
        self.base_dir = Path(base_dir)
        self.default_file_path = default_file_path

    async def dispatch_request(self, **kwargs):
        if 'path' in kwargs:
            requested_file = (self.base_dir / kwargs['path'])
            if requested_file.exists():
                return await send_file(requested_file)
        return await send_file(self.base_dir / self.default_file_path)


class ChatCompletion(View):
    def __init__(self, app, ctx, lock):
        self.app = app
        self.ctx = ctx
        self.lock = lock

    async def dispatch_request(self):
        app = self.app
        ctx = self.ctx
        await self.lock.acquire()
        async with app.app_context():
            if app.config['auth_token']:
                token = request.headers.get('Authorization')
                if token.split(" ")[1] != app.config['auth_token']:
                    abort(401)
            ctx[CONVERSE_RES_KEY] = asyncio.Queue()
            data = await request.get_json()
            model_name = data['model']

            agent = ctx.setdefault(CONVERSE_AGENTS_KEY, {}).get(model_name)
            if agent is None:
                abort(400, "model not found")

            messages = data.get('messages', [])
            last_user_message = next((m['content'] for m in reversed(messages) if m['role'] == 'user'), None)

            agent.message.value = last_user_message
            agent.conversation.value = messages

            is_stream = data.get('stream', False)

            if is_stream:
                return stream_with_context(self.run_with_stream_format)(agent), 200, {
                    'Content-Type': "text/event-stream"}
            else:
                return await self.run_with_single_format(agent)

    async def execute_with_output_finished_marker(self, agent):
        await SubGraphExecutor(agent).do_async(self.ctx)
        await self.ctx[CONVERSE_RES_KEY].put(None)

    async def run_with_stream_format(self, agent):
        try:
            yield ""
            chat_id = f"chatcmpl-{make_id()}"
            created = int(time.time())

            task = asyncio.create_task(self.execute_with_output_finished_marker(agent))
            while True:
                try:
                    maybe_response = await asyncio.wait_for(self.ctx[CONVERSE_RES_KEY].get(), timeout=10.0)
                    if maybe_response is not None:
                        yield f"data: {make_content_response(agent.name.value, chat_id, created, maybe_response)}\n\n"
                    else:
                        break
                except TimeoutError:
                    yield f"data: {make_content_response(agent.name.value, chat_id, created, '')}\n\n"
            await task

            yield f"data: {make_finish_response(agent.name.value, chat_id, created)}\n\n"
            yield "data: [DONE]\n\n"
        finally:
            self.lock.release()

    async def run_with_single_format(self, agent):
        try:
            chat_id = f"chatcmpl-{make_id()}"
            created = int(time.time())

            output = ""

            task = asyncio.create_task(self.execute_with_output_finished_marker(agent))
            while True:
                maybe_response = await self.ctx[CONVERSE_RES_KEY].get()
                if maybe_response is not None:
                    output = output + maybe_response
                else:
                    break
            await task

            async with self.app.app_context():
                return jsonify(
                    {
                        "id": chat_id,
                        "object": "chat.completion",
                        "created": created,
                        "choices": [{
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": output,
                            },
                            "finish_reason": "stop"
                        }],
                        "usage": {
                            "prompt_tokens": 0,
                            "completion_tokens": 0,
                            "total_tokens": 0
                        }
                    }
                )
        finally:
            self.lock.release()


class ModelsList(View):
    def __init__(self, app, ctx):
        self.app = app
        self.ctx = ctx

    async def dispatch_request(self):
        agents = self.ctx.setdefault(CONVERSE_AGENTS_KEY, {}).keys()
        async with self.app.app_context():
            return jsonify({
                "object": "list",
                "data": [
                    {
                        "id": agent,
                        "object": "model",
                        "created": 0,
                        "owned_by": "organization-owner"
                    }
                    for agent in agents
                ]
            })


@xai_component
class ConverseMakeServer(Component):
    secret_key: InArg[str]
    auth_token: InArg[str]
    max_timeout: InArg[int]


    def execute(self, ctx) -> None:
        lock = asyncio.Lock()
        public_dir = str(Path(inspect.getfile(inspect.currentframe())).parent.absolute() / "public")
        app = Quart(
            'converse',
            static_folder=public_dir,
            static_url_path=""
        )
        app = cors(app)
        app.secret_key = self.secret_key.value if self.secret_key.value is not None else 'opensesame'
        app.config['auth_token'] = self.auth_token.value
        app.config['RESPONSE_TIMEOUT'] = self.max_timeout.value if self.max_timeout.value is not None else 600


        index_routes = [
            '/technologic',
            '/technologic/',
            '/technologic/<path:path>'
        ]

        for index_route in index_routes:
            app.add_url_rule(
                index_route,
                endpoint=index_route.replace("/", "_"),
                methods=['GET'],
                view_func=SendFileRoute.as_view(index_route, public_dir + '/technologic/', 'index.html')
            )
        app.add_url_rule('/', endpoint='index', methods=['GET'], view_func=lambda: redirect('/technologic'))
        app.add_url_rule('/models', endpoint='models', methods=['GET'],
                         view_func=ModelsList.as_view("/models", app, ctx))
        app.add_url_rule('/chat/completions', methods=['POST'],
                         view_func=ChatCompletion.as_view('/chat/completions', app, ctx, lock))

        ctx[CONVERSE_APP_KEY] = app


@xai_component
class ConverseRun(Component):
    debug_mode: InArg[bool]

    def execute(self, ctx) -> None:
        app = ctx[CONVERSE_APP_KEY]

        loop = asyncio.get_event_loop()

        # Can't run debug mode from inside jupyter.
        server = app.run_task(
            debug=self.debug_mode.value if self.debug_mode.value is not None else False,
            host="0.0.0.0",
            port=8080
        )

        if loop.is_running():
            asyncio.create_task(server)
        else:
            loop.run_until_complete(server)


@xai_component(type='Start', color='red')
class ConverseDefineAgent(Component):
    name: InCompArg[str]
    message: OutArg[str]
    conversation: OutArg[list]

    def init(self, ctx):
        ctx.setdefault(CONVERSE_AGENTS_KEY, {})[self.name.value] = self


@xai_component(color='#8B008B')
class ConverseEmitResponse(AsyncComponent):
    """Adds the value to the current response

    ##### inPorts:
    - value: A string to be added to the response. If the value ands in a new line, it will be immediately flushed
    """
    value: InArg[str]

    async def execute(self, ctx):
        response = self.value.value
        await ctx[CONVERSE_RES_KEY].put(response)


@xai_component
class ConverseProcessCommand(Component):
    on_command: BaseComponent

    command_string: InCompArg[str]
    chat_response: InCompArg[str]

    command: OutArg[str]
    did_have_tool: OutArg[bool]
    result_list: OutArg[list]

    def execute(self, ctx) -> None:
        text = self.chat_response.value
        self.did_have_tool.value = self.command_string.value in text
        self.result_list.value = []

        if self.did_have_tool.value:
            lines = text.split("\n")
            for line in lines:
                if line.startswith(self.command_string.value):
                    command = line.split(":", 1)[1].strip()
                    self.command.value = command
                    try:
                        if hasattr(self, 'on_command'):
                            SubGraphExecutor(self.on_command).do(ctx)
                    except Exception as e:
                        import traceback
                        traceback.print_exc()
