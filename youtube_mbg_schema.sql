--
-- PostgreSQL database dump
--

-- Dumped from database version 17.0
-- Dumped by pg_dump version 17.0

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: komentar_youtube; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.komentar_youtube (
    comment_id character varying(255) NOT NULL,
    author character varying(255),
    komentar text,
    tanggal timestamp without time zone
);


ALTER TABLE public.komentar_youtube OWNER TO postgres;

--
-- Data for Name: komentar_youtube; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.komentar_youtube (comment_id, author, komentar, tanggal) FROM stdin;
UgzSi9cd_lWegvQJFSh4AaABAg	@papatnguaworr	jujur ak lebih suka masakam mama	2026-11-08 12:07:58
\.


--
-- Name: komentar_youtube komentar_youtube_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.komentar_youtube
    ADD CONSTRAINT komentar_youtube_pkey PRIMARY KEY (comment_id);


--
-- PostgreSQL database dump complete
--

