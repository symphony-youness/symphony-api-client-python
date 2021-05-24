import asyncio
from unittest.mock import MagicMock, AsyncMock, call

import pytest

from symphony.bdk.core.auth.auth_session import AuthSession
from symphony.bdk.core.config.loader import BdkConfigLoader
from symphony.bdk.core.service.datafeed.abstract_datafeed_loop import RealTimeEvent
from symphony.bdk.core.service.datafeed.datafeed_loop_v2 import DatafeedLoopV2
from symphony.bdk.core.service.datafeed.real_time_event_listener import RealTimeEventListener
from symphony.bdk.gen import ApiClient, ApiException
from symphony.bdk.gen.agent_api.datafeed_api import DatafeedApi
from symphony.bdk.gen.agent_model.ack_id import AckId
from symphony.bdk.gen.agent_model.datafeed import Datafeed
from symphony.bdk.gen.agent_model.v4_event import V4Event
from symphony.bdk.gen.agent_model.v4_initiator import V4Initiator
from symphony.bdk.gen.agent_model.v4_message_sent import V4MessageSent
from symphony.bdk.gen.agent_model.v4_payload import V4Payload
from symphony.bdk.gen.agent_model.v4_user import V4User
from tests.core.config import minimal_retry_config, minimal_retry_config_with_attempts
from tests.utils.resource_utils import get_config_resource_filepath


class EventsMock:
    def __init__(self, events):
        self.events = events
        self.ack_id = "ack_id"


@pytest.fixture(name="auth_session")
def fixture_auth_session():
    auth_session = AuthSession(None)
    auth_session.session_token = "session_token"
    auth_session.key_manager_token = "km_token"
    return auth_session


@pytest.fixture(name="config")
def fixture_config():
    config = BdkConfigLoader.load_from_file(get_config_resource_filepath("config.yaml"))
    config.datafeed.retry = minimal_retry_config()
    config.datafeed.version = "v2"
    return config


@pytest.fixture(name="datafeed_api")
def fixture_datafeed_api():
    datafeed_api = MagicMock(DatafeedApi)
    datafeed_api.api_client = MagicMock(ApiClient)
    datafeed_api.list_datafeed = AsyncMock()
    datafeed_api.create_datafeed = AsyncMock()
    datafeed_api.read_datafeed = AsyncMock()
    datafeed_api.delete_datafeed = AsyncMock()
    return datafeed_api


@pytest.fixture(name="mock_listener")
def fixture_mock_listener():
    return AsyncMock(wraps=RealTimeEventListener())


@pytest.fixture(name="initiator")
def fixture_initiator():
    return V4Initiator(user=V4User(username="username"))


@pytest.fixture(name="message_sent")
def fixture_message_sent(initiator):
    return V4Event(type=RealTimeEvent.MESSAGESENT.name,
                   payload=V4Payload(message_sent=V4MessageSent()),
                   initiator=initiator)


@pytest.fixture(name="message_sent_event")
def fixture_message_sent_event(message_sent):
    return EventsMock([message_sent])


@pytest.fixture(name="read_df_side_effect")
def fixture_read_df_side_effect(message_sent_event):
    async def read_df(**kwargs):
        await asyncio.sleep(0.001)  # to force the switching of tasks
        return message_sent_event

    return read_df


@pytest.fixture(name="datafeed_loop")
def fixture_datafeed_loop(datafeed_api, auth_session, config):
    datafeed_loop = DatafeedLoopV2(datafeed_api, auth_session, config)

    class RealTimeEventListenerImpl(RealTimeEventListener):

        async def on_message_sent(self, initiator: V4Initiator, event: V4MessageSent):
            await datafeed_loop.stop()

    datafeed_loop.subscribe(RealTimeEventListenerImpl())
    return datafeed_loop


@pytest.mark.asyncio
async def test_start(datafeed_loop, datafeed_api, read_df_side_effect):
    datafeed_api.list_datafeed.return_value = []
    datafeed_api.create_datafeed.return_value = Datafeed(id="test_id")
    datafeed_api.read_datafeed.side_effect = read_df_side_effect

    await datafeed_loop.start()

    datafeed_api.list_datafeed.assert_called_with(
        session_token="session_token",
        key_manager_token="km_token"
    )
    datafeed_api.create_datafeed.assert_called_with(
        session_token="session_token",
        key_manager_token="km_token"
    )
    assert datafeed_api.read_datafeed.call_args_list[0].kwargs == {"session_token": "session_token",
                                                                   "key_manager_token": "km_token",
                                                                   "datafeed_id": "test_id",
                                                                   "ack_id": AckId(ack_id="")}
    assert datafeed_loop._datafeed_id == "test_id"
    assert datafeed_loop._ack_id == "ack_id"


@pytest.mark.asyncio
async def test_start_datafeed_exist(datafeed_loop, datafeed_api, read_df_side_effect):
    datafeed_api.list_datafeed.return_value = [Datafeed(id="test_id_exist")]
    datafeed_api.read_datafeed.side_effect = read_df_side_effect

    await datafeed_loop.start()

    datafeed_api.list_datafeed.assert_called_with(
        session_token="session_token",
        key_manager_token="km_token"
    )
    assert datafeed_api.read_datafeed.call_args_list[0].kwargs == {"session_token": "session_token",
                                                                   "key_manager_token": "km_token",
                                                                   "datafeed_id": "test_id_exist",
                                                                   "ack_id": AckId(ack_id="")}
    assert datafeed_loop._datafeed_id == "test_id_exist"
    assert datafeed_loop._ack_id == "ack_id"


@pytest.mark.asyncio
async def test_start_datafeed_stale_datafeed(datafeed_loop, datafeed_api, message_sent_event):
    datafeed_loop._retry_config = minimal_retry_config_with_attempts(2)
    datafeed_api.list_datafeed.return_value = [Datafeed(id="fault_datafeed_id")]
    datafeed_api.create_datafeed.return_value = Datafeed(id="test_id")

    # This is done this way because side_effect with a list containing coroutines is not behaving as expected
    async def raise_and_return_event(**kwargs):
        if raise_and_return_event.first:
            raise_and_return_event.first = False
            raise ApiException(400)
        await asyncio.sleep(0.00001)  # to force the switching of tasks
        return message_sent_event

    raise_and_return_event.first = True

    datafeed_api.read_datafeed.side_effect = raise_and_return_event

    await datafeed_loop.start()

    datafeed_api.list_datafeed.assert_called_with(
        session_token="session_token",
        key_manager_token="km_token"
    )

    datafeed_api.delete_datafeed.assert_called_with(
        session_token="session_token",
        key_manager_token="km_token",
        datafeed_id="fault_datafeed_id"
    )

    datafeed_api.create_datafeed.assert_called_with(
        session_token="session_token",
        key_manager_token="km_token"
    )

    datafeed_api.read_datafeed.assert_has_calls([
        call(
            session_token="session_token",
            key_manager_token="km_token",
            datafeed_id="fault_datafeed_id",
            ack_id=AckId(ack_id="")
        ),
        call(
            session_token="session_token",
            key_manager_token="km_token",
            datafeed_id="test_id",
            ack_id=AckId(ack_id="")
        )
    ])

    assert datafeed_loop._datafeed_id == "test_id"
    assert datafeed_loop._ack_id == "ack_id"


@pytest.mark.asyncio
async def test_read_datafeed_no_value(datafeed_loop, datafeed_api):
    datafeed_api.read_datafeed.return_value = EventsMock(None)

    assert await datafeed_loop.read_datafeed() is None


@pytest.mark.asyncio
async def test_read_datafeed_empty_list(datafeed_loop, datafeed_api):
    datafeed_api.read_datafeed.return_value = EventsMock([])

    assert await datafeed_loop.read_datafeed() is None


@pytest.mark.asyncio
async def test_read_datafeed_non_empty_list(datafeed_loop, datafeed_api, message_sent):
    events = [message_sent]
    datafeed_api.read_datafeed.return_value = EventsMock(events)

    assert await datafeed_loop.read_datafeed() == events


@pytest.mark.asyncio
async def test_400_should_call_recreate_df_and_retry(datafeed_loop, datafeed_api):
    datafeed_loop._retry_config = minimal_retry_config_with_attempts(2)
    datafeed_loop.recreate_datafeed = AsyncMock()
    datafeed_api.read_datafeed.side_effect = [ApiException(status=400), ApiException(status=500)]

    with pytest.raises(ApiException) as exception:
        await datafeed_loop.start()
        assert exception.value.status == 500

    datafeed_loop.recreate_datafeed.assert_called_once()
    assert datafeed_api.read_datafeed.call_count == 2


@pytest.mark.asyncio
async def test_400_should_call_recreate_df_return_and_retry(datafeed_loop, datafeed_api, message_sent_event):
    async def read_df(**kwargs):
        if read_df.first_time:
            read_df.first_time = False
            raise ApiException(status=400, reason="")
        await asyncio.sleep(0.00001)  # to force the switching of tasks
        return message_sent_event

    read_df.first_time = True

    datafeed_api.read_datafeed.side_effect = read_df
    datafeed_loop._retry_config = minimal_retry_config_with_attempts(2)
    datafeed_loop.prepare_datafeed = AsyncMock()
    datafeed_loop.recreate_datafeed = AsyncMock()

    await datafeed_loop.start()

    datafeed_loop.recreate_datafeed.assert_called_once()
    assert datafeed_api.read_datafeed.call_count >= 2


@pytest.mark.asyncio
async def test_unexpected_error_should_be_propagated_and_call_stop_tasks(datafeed_loop, datafeed_api):
    exception = ValueError("An error")
    datafeed_api.read_datafeed.side_effect = exception

    datafeed_loop.prepare_datafeed = AsyncMock()
    datafeed_loop.recreate_datafeed = AsyncMock()
    datafeed_loop._stop_listener_tasks = AsyncMock()

    with pytest.raises(ValueError) as raised_exception:
        await datafeed_loop.start()
        assert raised_exception == exception

    datafeed_loop.prepare_datafeed.assert_called_once()
    datafeed_api.read_datafeed.assert_called_once()
    datafeed_loop.recreate_datafeed.assert_not_called()
    datafeed_loop._stop_listener_tasks.assert_called_once()
