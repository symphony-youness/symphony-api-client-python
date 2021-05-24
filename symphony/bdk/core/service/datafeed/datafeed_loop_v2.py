from typing import Optional

from symphony.bdk.core.auth.auth_session import AuthSession
from symphony.bdk.core.config.model.bdk_config import BdkConfig
from symphony.bdk.core.service.datafeed.abstract_datafeed_loop import AbstractDatafeedLoop
from symphony.bdk.core.retry import retry
from symphony.bdk.core.retry.strategy import read_datafeed_retry
from symphony.bdk.gen.agent_api.datafeed_api import DatafeedApi
from symphony.bdk.gen.agent_model.ack_id import AckId
from symphony.bdk.gen.agent_model.v5_datafeed import V5Datafeed


class DatafeedLoopV2(AbstractDatafeedLoop):
    """A class for implementing the datafeed v2 loop service.

        This service will be started by calling :func:`~DatafeedLoopV2.start`.

        On the very first run, the BDK bot will try to retrieve the list of datafeed to which it is listening.
        Since each bot should only listening to just one datafeed, the first datafeed in the list will be used by
        the bot to be listened to. If the retrieved list is empty, the BDK bot will create a new datafeed to listen.

        The BDK bot will listen to this datafeed to get all the received real-time events.

        If this datafeed becomes stale or faulty, the BDK bot will create the new one for listening.

        This service will be stopped by calling :func:`~DatafeedLoopV1.stop`

        If the datafeed service is stopped during a read datafeed call, it has to wait until the last read finish to be
        really stopped
        """

    def __init__(self, datafeed_api: DatafeedApi, auth_session: AuthSession, config: BdkConfig):
        super().__init__(datafeed_api, auth_session, config)
        self._ack_id = ""
        self._datafeed_id = None

    async def prepare_datafeed(self):
        datafeed = await self._retrieve_datafeed()
        if not datafeed:
            datafeed = await self._create_datafeed()
        self._datafeed_id = datafeed.id

    @retry(retry=read_datafeed_retry)
    async def read_datafeed(self):
        params = {
            "session_token": await self._auth_session.session_token,
            "key_manager_token": await self._auth_session.key_manager_token,
            "datafeed_id": self._datafeed_id,
            "ack_id": AckId(ack_id=self._ack_id)
        }
        event_list = await self._datafeed_api.read_datafeed(**params)
        self._ack_id = event_list.ack_id
        if event_list.events:
            return event_list.events

    async def recreate_datafeed(self):
        await self._delete_datafeed()
        datafeed = await self._create_datafeed()

        self._datafeed_id = datafeed.id
        self._ack_id = ""

    @retry
    async def _retrieve_datafeed(self) -> Optional[V5Datafeed]:
        session_token = await self._auth_session.session_token
        key_manager_token = await self._auth_session.key_manager_token
        datafeeds = await self._datafeed_api.list_datafeed(session_token=session_token,
                                                           key_manager_token=key_manager_token)
        if datafeeds:
            return datafeeds[0]
        return None

    @retry
    async def _create_datafeed(self) -> V5Datafeed:
        session_token = await self._auth_session.session_token
        key_manager_token = await self._auth_session.key_manager_token

        return await self._datafeed_api.create_datafeed(session_token=session_token, key_manager_token=key_manager_token)

    @retry
    async def _delete_datafeed(self) -> None:
        session_token = await self._auth_session.session_token
        key_manager_token = await self._auth_session.key_manager_token
        await self._datafeed_api.delete_datafeed(datafeed_id=self._datafeed_id,
                                                 session_token=session_token,
                                                 key_manager_token=key_manager_token)
