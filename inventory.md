# Database Access Inventory
| File Path | Function/Class | Operation Type | Description |
| --- | --- | --- | --- |
| Backend/app.py | Function: fail_interrupted_jobs | Read | Performs DB operations using SQLAlchemy/psycopg |
| Backend/app.py | Function: readiness_check | Read/Write (Raw) | Performs DB operations using SQLAlchemy/psycopg |
| Backend/jwiz.py | Function: find_result_cards | Read | Performs DB operations using SQLAlchemy/psycopg |
| Backend/jwiz.py | Function: extract_phone | Read | Performs DB operations using SQLAlchemy/psycopg |
| Backend/jwiz.py | Function: extract_email | Read | Performs DB operations using SQLAlchemy/psycopg |
| Backend/jwiz.py | Function: extract_profile_email | Read | Performs DB operations using SQLAlchemy/psycopg |
| Backend/jwiz.py | Function: extract_profile_phone | Read | Performs DB operations using SQLAlchemy/psycopg |
| Backend/agents\orchestrator.py | Function: handle_message | Read | Performs DB operations using SQLAlchemy/psycopg |
| Backend/agents\decisions\data_availability.py | Function: evaluate | Read | Performs DB operations using SQLAlchemy/psycopg |
| Backend/agents\specialized\database_agent.py | Function: search_leads | Read | Performs DB operations using SQLAlchemy/psycopg |
| Backend/agents\specialized\database_agent.py | Function: count_matching_leads | Read | Performs DB operations using SQLAlchemy/psycopg |
| Backend/agents\specialized\database_agent.py | Function: search_datasets | Read | Performs DB operations using SQLAlchemy/psycopg |
| Backend/agents\specialized\database_agent.py | Function: list_jobs | Read | Performs DB operations using SQLAlchemy/psycopg |
| Backend/agents\specialized\growth_agent.py | Function: _audit | Write/Transaction | Performs DB operations using SQLAlchemy/psycopg |
| Backend/agents\specialized\sales_agent.py | Function: _audit | Write/Transaction | Performs DB operations using SQLAlchemy/psycopg |
| Backend/agents\workflow\collaboration.py | Function: execute | Read/Write (Raw) | Performs DB operations using SQLAlchemy/psycopg |
| Backend/database\base.py | Class: Base | DDL/ORM | SQLAlchemy model definition |
| Backend/database\models\action.py | Class: AgentAction | DDL/ORM | SQLAlchemy model definition |
| Backend/database\models\agent.py | Class: Agent | DDL/ORM | SQLAlchemy model definition |
| Backend/database\models\contact.py | Class: Contact | DDL/ORM | SQLAlchemy model definition |
| Backend/database\models\dataset.py | Class: Dataset | DDL/ORM | SQLAlchemy model definition |
| Backend/database\models\dataset.py | Class: DatasetRecord | DDL/ORM | SQLAlchemy model definition |
| Backend/database\models\department.py | Class: Department | DDL/ORM | SQLAlchemy model definition |
| Backend/database\models\email.py | Class: Email | DDL/ORM | SQLAlchemy model definition |
| Backend/database\models\job.py | Class: Job | DDL/ORM | SQLAlchemy model definition |
| Backend/database\models\lead.py | Class: Lead | DDL/ORM | SQLAlchemy model definition |
| Backend/database\models\location.py | Class: Location | DDL/ORM | SQLAlchemy model definition |
| Backend/database\models\message.py | Class: AgentMessage | DDL/ORM | SQLAlchemy model definition |
| Backend/database\models\organization.py | Class: Organization | DDL/ORM | SQLAlchemy model definition |
| Backend/database\models\phone.py | Class: Phone | DDL/ORM | SQLAlchemy model definition |
| Backend/database\models\query.py | Class: Query | DDL/ORM | SQLAlchemy model definition |
| Backend/database\models\requirement.py | Class: Requirement | DDL/ORM | SQLAlchemy model definition |
| Backend/database\models\scrape_run.py | Class: ScrapeRun | DDL/ORM | SQLAlchemy model definition |
| Backend/database\models\session.py | Class: AgentSession | DDL/ORM | SQLAlchemy model definition |
| Backend/database\models\source.py | Class: Source | DDL/ORM | SQLAlchemy model definition |
| Backend/database\models\user.py | Class: User | DDL/ORM | SQLAlchemy model definition |
| Backend/migrations\env.py | Function: run_migrations_offline | Read/Write (Raw) | Performs DB operations using SQLAlchemy/psycopg |
| Backend/repositories\agent_sessions.py | Function: get_by_code | Read | Performs DB operations using SQLAlchemy/psycopg |
| Backend/repositories\agent_sessions.py | Function: get_active_session | Read | Performs DB operations using SQLAlchemy/psycopg |
| Backend/repositories\agent_sessions.py | Function: list_by_session | Read | Performs DB operations using SQLAlchemy/psycopg |
| Backend/repositories\contacts.py | Function: get_by_normalized_name | Read | Performs DB operations using SQLAlchemy/psycopg |
| Backend/repositories\contacts.py | Function: search_by_name | Read | Performs DB operations using SQLAlchemy/psycopg |
| Backend/repositories\contacts.py | Function: get_by_linkedin | Read | Performs DB operations using SQLAlchemy/psycopg |
| Backend/repositories\leads.py | Function: get_by_organization_and_contact | Read | Performs DB operations using SQLAlchemy/psycopg |
| Backend/repositories\leads.py | Function: count_by_status | Read | Performs DB operations using SQLAlchemy/psycopg |
| Backend/repositories\leads.py | Function: search_leads | Read | Performs DB operations using SQLAlchemy/psycopg |
| Backend/repositories\organizations.py | Function: get_by_name | Read | Performs DB operations using SQLAlchemy/psycopg |
| Backend/repositories\organizations.py | Function: get_by_domain | Read | Performs DB operations using SQLAlchemy/psycopg |
| Backend/repositories\organizations.py | Function: get_by_website | Read | Performs DB operations using SQLAlchemy/psycopg |
| Backend/repositories\organizations.py | Function: search_by_name | Read | Performs DB operations using SQLAlchemy/psycopg |
| Backend/repositories\queries.py | Function: list_by_session | Read | Performs DB operations using SQLAlchemy/psycopg |
| Backend/repositories\queries.py | Function: get_latest_for_session | Read | Performs DB operations using SQLAlchemy/psycopg |
| Backend/repositories\requirements.py | Function: get_by_session | Read | Performs DB operations using SQLAlchemy/psycopg |